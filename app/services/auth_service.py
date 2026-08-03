from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    is_token_revoked,
    revoke_token,
    verify_password,
)
from app.db.models.user import User, UserRole
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserOut


def _build_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
    )


def _build_auth_response(user: User) -> AuthResponse:
    tokens = _build_tokens(user)
    return AuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        user=_user_to_out(user),
    )


def _user_to_out(user: User) -> UserOut:
    return UserOut(
        id=str(user.id),
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        avatar=user.avatar,
        role=user.role.value if hasattr(user.role, "value") else user.role,
        addresses=[
            {
                "id": str(a.id),
                "label": a.label,
                "street": a.street,
                "city": a.city,
                "state": a.state,
                "postal_code": a.postal_code,
                "country": a.country,
                "is_default": a.is_default,
            }
            for a in user.addresses
        ],
        created_at=user.created_at,
    )


async def register(db: AsyncSession, data: RegisterRequest) -> AuthResponse:
    # Check email uniqueness
    existing = await db.scalar(select(User).where(User.email == data.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        password_hash=await hash_password(data.password),
        phone=data.phone,
        role=UserRole.CUSTOMER,
    )
    db.add(user)
    await db.commit()

    # Reload with addresses relationship for _user_to_out
    result = await db.execute(
        select(User).options(selectinload(User.addresses)).where(User.id == user.id)
    )
    user = result.scalar_one()

    return _build_auth_response(user)


async def login(db: AsyncSession, data: LoginRequest) -> AuthResponse:
    result = await db.execute(
        select(User)
        .options(selectinload(User.addresses))
        .where(User.email == data.email)
    )
    user = result.scalar_one_or_none()

    if not user or not await verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return _build_auth_response(user)


async def refresh_tokens(
    db: AsyncSession, redis: Redis, refresh_token: str
) -> TokenResponse:
    payload = decode_token(refresh_token)
    user_id = payload.get("sub")
    token_type = payload.get("type")

    if not user_id or token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Without this, a logged-out refresh token could still mint fresh access
    # tokens and defeat logout entirely
    if await is_token_revoked(redis, payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
        )

    user = await db.scalar(
        select(User).where(User.id == UUID(user_id), User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return _build_tokens(user)


async def logout(
    redis: Redis,
    user_id: UUID,
    access_token: str,
    refresh_token: str | None = None,
) -> None:
    """Revoke the caller's access token, and its refresh token if supplied.

    Deliberately idempotent and never raises: logging out twice, or with an
    already-expired token, still succeeds. A refresh token belonging to a
    different user is ignored rather than rejected, so one account cannot
    revoke another's session.
    """
    await revoke_token(redis, decode_token(access_token))

    if refresh_token:
        payload = decode_token(refresh_token)
        if payload.get("sub") == str(user_id) and payload.get("type") == "refresh":
            await revoke_token(redis, payload)


async def get_me(db: AsyncSession, user_id: UUID) -> UserOut:
    result = await db.execute(
        select(User).options(selectinload(User.addresses)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_out(user)


async def update_me(db: AsyncSession, user_id: UUID, data: dict) -> UserOut:
    result = await db.execute(
        select(User).options(selectinload(User.addresses)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for key, value in data.items():
        if value is not None and hasattr(user, key):
            setattr(user, key, value)

    await db.commit()
    return _user_to_out(user)
