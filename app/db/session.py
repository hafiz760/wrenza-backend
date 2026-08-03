from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine_args = {
    "echo": settings.DEBUG,
    "pool_size": 20,
    "max_overflow": 10,
    "pool_pre_ping": True,
}
if settings.DATABASE_SSL:
    engine_args["connect_args"] = {"ssl": True}

engine = create_async_engine(settings.DATABASE_URL, **engine_args)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
