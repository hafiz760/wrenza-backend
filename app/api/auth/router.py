from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from app.core.deps import CurrentUser, DbSession, RedisClient, security_scheme
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse
from app.schemas.user import UserOut, UserUpdate
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=AuthResponse)
async def register(data: RegisterRequest, db: DbSession):
    return await auth_service.register(db, data)


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
    # TODO: Generate reset token and enqueue email task
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, db: DbSession):
    # TODO: Validate token and update password
    return MessageResponse(message="Password has been reset successfully.")
