from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import structlog

from app.core.security import (
    create_access_token,
    create_password_reset_token,
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
from app.services.email_verification import (
    consume_email_verification_code,
    consume_password_reset_code,
    issue_email_verification_code,
    issue_password_reset_code,
)
from app.tasks.queue import enqueue

logger = structlog.get_logger()


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
        email_verified=user.email_verified_at is not None,
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


async def register(db: AsyncSession, redis: Redis, data: RegisterRequest) -> None:
    normalized_email = str(data.email).strip().lower()
    existing = await db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        email=normalized_email,
        password_hash=await hash_password(data.password),
        phone=data.phone,
        role=UserRole.CUSTOMER,
    )
    db.add(user)
    await db.commit()

    queued = await issue_email_verification_code(redis, normalized_email)
    if not queued:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Your account was created, but the verification email could not be "
                "queued. Request a new code to continue."
            ),
        )


async def resend_email_verification(db: AsyncSession, redis: Redis, email: str) -> None:
    normalized_email = email.strip().lower()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if not user or not user.is_active or user.email_verified_at is not None:
        return

    queued = await issue_email_verification_code(redis, normalized_email)
    if not queued:
        logger.info("Verification resend skipped", email=normalized_email)


async def verify_email(
    db: AsyncSession, redis: Redis, email: str, code: str
) -> AuthResponse:
    normalized_email = email.strip().lower()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    invalid_code = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The verification code is invalid or expired.",
    )
    if (
        not user
        or not user.is_active
        or user.email_verified_at is not None
        or not await consume_email_verification_code(redis, normalized_email, code)
    ):
        raise invalid_code

    user.email_verified_at = datetime.now(timezone.utc)
    await db.commit()

    result = await db.execute(
        select(User)
        .options(selectinload(User.addresses))
        .where(User.id == user.id)
    )
    verified_user = result.scalar_one()
    return _build_auth_response(verified_user)


async def login(db: AsyncSession, data: LoginRequest) -> AuthResponse:
    result = await db.execute(
        select(User)
        .options(selectinload(User.addresses))
        .where(func.lower(User.email) == str(data.email).strip().lower())
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

    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address before signing in.",
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
        select(User).where(
            User.id == UUID(user_id),
            User.is_active.is_(True),
            User.email_verified_at.is_not(None),
        )
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


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Issue a reset token and queue the email.

    Silent about whether the account exists — the endpoint answers identically
    either way. A reply that differs by account would let anyone check which
    of their addresses are registered here.
    """
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        logger.info("Password reset requested for unknown email", email=email)
        return

    token = create_password_reset_token(user.id)
    await enqueue("send_password_reset", user.email, token)


async def request_password_reset_otp(
    db: AsyncSession, redis: Redis, email: str
) -> None:
    """Queue a reset OTP for an active, verified account, if one exists."""
    normalized_email = email.strip().lower()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if (
        not user
        or user.role != UserRole.CUSTOMER
        or not user.is_active
        or user.email_verified_at is None
    ):
        logger.info("Password reset OTP skipped")
        return

    queued = await issue_password_reset_code(redis, normalized_email)
    if not queued:
        logger.info("Password reset OTP not queued")


async def verify_password_reset_otp(
    db: AsyncSession, redis: Redis, email: str, code: str
) -> str:
    """Consume a reset OTP and issue the token used by the password update API."""
    normalized_email = email.strip().lower()
    user = await db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if (
        not user
        or user.role != UserRole.CUSTOMER
        or not user.is_active
        or user.email_verified_at is None
        or not await consume_password_reset_code(redis, normalized_email, code)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The verification code is invalid or expired.",
        )

    return create_password_reset_token(user.id)


async def reset_password(
    db: AsyncSession, redis: Redis, token: str, new_password: str
) -> None:
    """Consume a reset token and set the new password.

    The same 400 covers every failure — expired, forged, wrong purpose, already
    used. Distinguishing them would tell an attacker which part to fix.
    """
    payload = decode_token(token)

    # Checked against `type`, the same field the auth dependency screens on,
    # so the two can never disagree about what a token is for.
    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    if await is_token_revoked(redis, payload):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user = await db.scalar(select(User).where(User.id == payload.get("sub")))
    if not user:
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user.password_hash = await hash_password(new_password)
    await db.commit()

    # Spend the token: the link stays in the inbox forever, so without this a
    # second click would reset the password again.
    await revoke_token(redis, payload)
