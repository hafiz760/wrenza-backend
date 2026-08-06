import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import bcrypt
from jose import JWTError, jwt
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

DENYLIST_PREFIX = "denylist:"


def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


async def hash_password(plain: str) -> str:
    """Hash password using bcrypt in a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(_hash, plain)


async def verify_password(plain: str, hashed: str) -> bool:
    """Verify password using bcrypt in a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(_verify, plain, hashed)


def hash_password_sync(plain: str) -> str:
    """Synchronous version for use in tests and scripts."""
    return _hash(plain)


def create_access_token(user_id: UUID, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "type": "access",
        # Unique per token so logout can revoke this one without touching
        # the same user's tokens on other devices
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "refresh",
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_password_reset_token(user_id: UUID) -> str:
    """Short-lived, single-purpose token for a reset link.

    `type` is `password_reset`, not `access`. That matters in both directions:
    the auth dependency rejects any token whose type is not `access`, so this
    one cannot be pasted as a bearer token to act as the user — and the reset
    handler rejects anything that is not `password_reset`, so a stolen session
    token cannot change a password.

    Getting this wrong is not theoretical: with `type: access` the link emailed
    to a customer doubled as a 30-minute API session for their account.

    The `jti` lets the existing denylist mark it spent — one click, one reset,
    even though the link stays in the inbox forever.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "password_reset",
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return {}


async def revoke_token(redis: Redis, payload: dict) -> None:
    """Denylist a token until it would have expired on its own.

    The Redis key's TTL matches the token's remaining life, so the denylist
    never grows without bound. Tokens issued before `jti` existed cannot be
    revoked; they are left to expire.
    """
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return

    ttl = int(exp - datetime.now(timezone.utc).timestamp())
    if ttl <= 0:
        return  # already expired — nothing to revoke

    try:
        await redis.set(f"{DENYLIST_PREFIX}{jti}", "1", ex=ttl)
    except RedisError:
        # Fail open: logout still reports success rather than 500ing. The token
        # keeps working until it expires, which is the pre-denylist behaviour.
        pass


async def is_token_revoked(redis: Redis, payload: dict) -> bool:
    """Check the denylist, failing open if Redis is unreachable.

    A Redis outage must not lock every logged-in user out, so an unreachable
    denylist is treated as empty — matching how auth behaved before it existed.
    """
    jti = payload.get("jti")
    if not jti:
        return False  # pre-`jti` token; nothing to match against

    try:
        return bool(await redis.exists(f"{DENYLIST_PREFIX}{jti}"))
    except RedisError:
        return False
