"""Short-lived email OTPs for account verification and password recovery."""

import hashlib
import hmac
import secrets

import structlog
from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.security import encrypt_email_verification_code
from app.tasks.queue import enqueue

logger = structlog.get_logger()

_KEY_PREFIX = "wz:email-verification:"

_CONSUME_CODE_SCRIPT = """
local stored = redis.call('GET', KEYS[1])
if not stored then
    return -1
end

if stored == ARGV[1] then
    redis.call('DEL', KEYS[1], KEYS[2])
    return 1
end

local attempts = redis.call('INCR', KEYS[2])
if attempts == 1 then
    local ttl = redis.call('TTL', KEYS[1])
    if ttl > 0 then
        redis.call('EXPIRE', KEYS[2], ttl)
    end
end

if attempts >= tonumber(ARGV[2]) then
    redis.call('DEL', KEYS[1], KEYS[2])
    return -2
end

return 0
"""


def _keys(email: str, purpose: str = "email-verification") -> tuple[str, str, str]:
    email_hash = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
    prefix = _KEY_PREFIX if purpose == "email-verification" else f"wz:{purpose}:"
    root = f"{prefix}{email_hash}"
    return f"{root}:code", f"{root}:attempts", f"{root}:cooldown"


def _code_digest(email: str, code: str) -> str:
    settings = get_settings()
    message = f"{email.strip().lower()}:{code}".encode("utf-8")
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


async def _issue_code(redis: Redis, email: str, purpose: str, job_name: str) -> bool:
    """Store a hashed one-time code and queue its encrypted email copy.

    Returns False when the address is still in its resend cooldown or when the
    queue did not accept the email job. No plaintext code is stored in Redis.
    """
    settings = get_settings()
    normalized_email = email.strip().lower()
    code_key, attempts_key, cooldown_key = _keys(normalized_email, purpose)

    try:
        accepted = await redis.set(
            cooldown_key,
            "1",
            ex=settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS,
            nx=True,
        )
        if not accepted:
            return False

        code = f"{secrets.randbelow(1_000_000):06d}"
        await redis.set(
            code_key,
            _code_digest(normalized_email, code),
            ex=settings.EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES * 60,
        )
        await redis.delete(attempts_key)
        queued = await enqueue(
            job_name,
            normalized_email,
            encrypt_email_verification_code(code),
        )
    except RedisError as exc:
        try:
            await redis.delete(code_key, attempts_key, cooldown_key)
        except RedisError:
            pass
        logger.error(
            "One-time code service unavailable", purpose=purpose, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="One-time code delivery is temporarily unavailable. Please try again.",
        ) from exc

    if not queued:
        try:
            await redis.delete(code_key, attempts_key, cooldown_key)
        except RedisError:
            logger.warning("Could not clear OTP state after queue failure")
        return False

    return True


async def issue_email_verification_code(redis: Redis, email: str) -> bool:
    """Issue an email-verification code without changing the registration flow."""
    return await _issue_code(
        redis, email, "email-verification", "send_email_verification_code"
    )


async def issue_password_reset_code(redis: Redis, email: str) -> bool:
    """Issue a password-reset code kept separate from registration codes."""
    return await _issue_code(
        redis, email, "password-reset", "send_password_reset_code"
    )


async def _consume_code(redis: Redis, email: str, code: str, purpose: str) -> bool:
    """Atomically check and consume a code, limiting guesses to five."""
    settings = get_settings()
    normalized_email = email.strip().lower()
    code_key, attempts_key, _cooldown_key = _keys(normalized_email, purpose)

    try:
        consume_code = redis.register_script(_CONSUME_CODE_SCRIPT)
        result = await consume_code(
            keys=[code_key, attempts_key],
            args=[
                _code_digest(normalized_email, code),
                settings.EMAIL_VERIFICATION_MAX_ATTEMPTS,
            ],
        )
    except RedisError as exc:
        logger.error(
            "One-time code service unavailable", purpose=purpose, error=str(exc)
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="One-time code verification is temporarily unavailable. Please try again.",
        ) from exc

    return result == 1


async def consume_email_verification_code(redis: Redis, email: str, code: str) -> bool:
    """Consume a registration code, preserving the existing verification flow."""
    return await _consume_code(redis, email, code, "email-verification")


async def consume_password_reset_code(redis: Redis, email: str, code: str) -> bool:
    """Consume a password-reset code; it cannot verify a new registration."""
    return await _consume_code(redis, email, code, "password-reset")
