import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db, get_redis
from app.core.security import create_access_token, hash_password_sync
from app.db.base import Base
from app.main import app

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


# Fake Redis — dict-backed so writes are actually readable. An AsyncMock that
# always answers None makes denylist tests pass vacuously: the revoked token
# never looks revoked. TTLs are ignored; tests do not depend on expiry.
class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, **kwargs):
        self.store[key] = value
        return True

    async def exists(self, *keys):
        return sum(1 for k in keys if k in self.store)

    async def delete(self, *keys):
        return sum(1 for k in keys if self.store.pop(k, None) is not None)

    async def scan(self, cursor=0, match=None, count=None):
        return (0, [])

    def flush(self):
        self.store.clear()


mock_redis = FakeRedis()


def override_get_redis():
    return mock_redis


@pytest_asyncio.fixture(autouse=True)
async def clear_redis():
    """Keep denylist entries from leaking between tests."""
    mock_redis.flush()
    yield


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_redis] = override_get_redis


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user():
    from app.db.models.user import User, UserRole

    async with TestingSessionLocal() as db:
        user = User(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password_hash=hash_password_sync("password123"),
            role=UserRole.CUSTOMER,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def admin_user():
    from app.db.models.user import User, UserRole

    async with TestingSessionLocal() as db:
        user = User(
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password_hash=hash_password_sync("admin123"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    token = create_access_token(test_user.id, test_user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_headers(admin_user):
    token = create_access_token(admin_user.id, admin_user.role.value)
    return {"Authorization": f"Bearer {token}"}
