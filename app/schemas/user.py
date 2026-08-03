from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import CamelModel


class AddressCreate(CamelModel):
    label: Annotated[str, Field(min_length=1, max_length=50)]
    street: Annotated[str, Field(min_length=1, max_length=255)]
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    country: Annotated[str, Field(min_length=1, max_length=100)] = "Pakistan"
    is_default: bool = False


class AddressUpdate(CamelModel):
    label: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    street: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    city: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    state: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    postal_code: Annotated[str, Field(min_length=1, max_length=20)] | None = None
    country: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    is_default: bool | None = None


class AddressOut(CamelModel):
    id: str
    label: str
    street: str
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool


class UserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    avatar: str | None = None
    role: Literal["customer", "admin", "manager"]
    addresses: list[AddressOut] = Field(default_factory=list)
    created_at: datetime


class UserUpdate(CamelModel):
    first_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    phone: (
        Annotated[str, Field(min_length=7, max_length=20, pattern=r"^[0-9+()\-\s]+$")]
        | None
    ) = None
    avatar: Annotated[str, Field(min_length=1, max_length=500)] | None = None


class AdminUserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: str
    is_active: bool
    created_at: datetime


class AdminUserUpdate(CamelModel):
    role: Literal["customer", "admin", "manager"] | None = None
    is_active: bool | None = None
