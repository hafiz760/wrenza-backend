from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession, RedisClient, security_scheme
from app.core.limiter import limiter
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    PasswordResetTokenResponse,
    ResendEmailVerificationRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyPasswordResetOtpRequest,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserOut, UserUpdate
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


def auth_rate_limit(limit: str):
    """Apply auth endpoint limits only when enabled for this environment."""
    if get_settings().AUTH_RATE_LIMITS_ENABLED:
        return limiter.limit(limit)
    return lambda endpoint: endpoint


@router.post(
    "/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED
)
@auth_rate_limit("5/hour")
async def register(
    request: Request,
    data: RegisterRequest,
    db: DbSession,
    redis: RedisClient,
):
    await auth_service.register(db, redis, data)
    return MessageResponse(message="Verification code sent. Check your email.")


@router.post("/verify-email", response_model=AuthResponse)
@auth_rate_limit("10/minute")
async def verify_email(
    request: Request,
    data: VerifyEmailRequest,
    db: DbSession,
    redis: RedisClient,
):
    return await auth_service.verify_email(db, redis, data.email, data.code)


@router.post("/resend-verification", response_model=MessageResponse)
@auth_rate_limit("3/minute")
async def resend_verification(
    request: Request,
    data: ResendEmailVerificationRequest,
    db: DbSession,
    redis: RedisClient,
):
    await auth_service.resend_email_verification(db, redis, data.email)
    return MessageResponse(
        message="If the account exists and needs verification, a code has been sent."
    )


@router.post("/login", response_model=AuthResponse)
async def login(data: LoginRequest, db: DbSession):
    return await auth_service.login(db, data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: DbSession, redis: RedisClient):
    return await auth_service.refresh_tokens(db, redis, data.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    user: CurrentUser,
    redis: RedisClient,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security_scheme)],
    data: LogoutRequest | None = None,
):
    """Revoke this device's tokens. Other devices stay signed in."""
    await auth_service.logout(
        redis,
        user.id,
        credentials.credentials,
        data.refresh_token if data else None,
    )
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser, db: DbSession):
    return await auth_service.get_me(db, user.id)


@router.put("/me", response_model=UserOut)
async def update_me(data: UserUpdate, user: CurrentUser, db: DbSession):
    update_data = data.model_dump(exclude_unset=True)
    return await auth_service.update_me(db, user.id, update_data)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(data: ForgotPasswordRequest, db: DbSession):
    """Send a reset link, if the address belongs to an account.

    The reply is identical either way. Saying "no such account" would let
    anyone test which addresses are registered here.
    """
    await auth_service.request_password_reset(db, data.email)
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/forgot-password-otp", response_model=MessageResponse)
@auth_rate_limit("5/hour")
async def forgot_password_otp(
    request: Request,
    data: ForgotPasswordRequest,
    db: DbSession,
    redis: RedisClient,
):
    """Send a short-lived reset code without disclosing whether an account exists."""
    await auth_service.request_password_reset_otp(db, redis, data.email)
    return MessageResponse(
        message=(
            "If an account with that email exists, a password reset code has been sent."
        )
    )


@router.post(
    "/verify-password-reset-otp", response_model=PasswordResetTokenResponse
)
@auth_rate_limit("10/minute")
async def verify_password_reset_otp(
    request: Request,
    data: VerifyPasswordResetOtpRequest,
    db: DbSession,
    redis: RedisClient,
):
    """Verify a reset code and return a short-lived password reset token."""
    reset_token = await auth_service.verify_password_reset_otp(
        db, redis, data.email, data.code
    )
    return PasswordResetTokenResponse(reset_token=reset_token)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, db: DbSession, redis: RedisClient):
    """Set a new password from a reset link. The link works once."""
    await auth_service.reset_password(db, redis, data.token, data.new_password)
    return MessageResponse(message="Password has been reset successfully.")
