from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.security import decode_token, is_token_revoked
from app.db.session import AsyncSessionLocal

security_scheme = HTTPBearer()
optional_security_scheme = HTTPBearer(auto_error=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    from app.db.models.user import User

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    token_type = payload.get("type")

    if not user_id or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if await is_token_revoked(redis, payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    result = await db.execute(
        select(User)
        .options(selectinload(User.addresses))
        .where(User.id == UUID(user_id), User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_current_user_optional(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(optional_security_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
):
    if not credentials:
        return None

    from app.db.models.user import User

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")

    if not user_id:
        return None

    if await is_token_revoked(redis, payload):
        return None  # treated as a guest, matching other invalid-token paths

    result = await db.execute(
        select(User).where(User.id == UUID(user_id), User.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def require_admin(
    user=Depends(get_current_user),
):
    if user.role not in ("admin", "manager"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# Type aliases for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated["User", Depends(get_current_user)]
OptionalUser = Annotated["User | None", Depends(get_current_user_optional)]
AdminUser = Annotated["User", Depends(require_admin)]
RedisClient = Annotated[Redis, Depends(get_redis)]
AppSettings = Annotated[Settings, Depends(get_settings)]
