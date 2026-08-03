from typing import Annotated

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel


PasswordStr = Annotated[str, Field(min_length=8, max_length=128)]
NameStr = Annotated[str, Field(min_length=1, max_length=100)]
PhoneStr = Annotated[
    str, Field(min_length=7, max_length=20, pattern=r"^[0-9+()\-\s]+$")
]


class LoginRequest(CamelModel):
    email: EmailStr
    password: PasswordStr


class RegisterRequest(CamelModel):
    first_name: NameStr
    last_name: NameStr
    email: EmailStr
    password: PasswordStr
    phone: PhoneStr | None = None


class TokenResponse(CamelModel):
    access_token: str
    refresh_token: str


class AuthResponse(CamelModel):
    access_token: str
    refresh_token: str
    user: "UserOut"


from app.schemas.user import UserOut

AuthResponse.model_rebuild()


class RefreshRequest(CamelModel):
    refresh_token: Annotated[str, Field(min_length=1, max_length=500)]


class LogoutRequest(CamelModel):
    """Optional body — supply the refresh token to revoke it alongside the
    access token, otherwise only the access token is revoked."""

    refresh_token: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class ForgotPasswordRequest(CamelModel):
    email: EmailStr


class ResetPasswordRequest(CamelModel):
    token: Annotated[str, Field(min_length=1, max_length=500)]
    new_password: PasswordStr
