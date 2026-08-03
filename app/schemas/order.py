from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import CamelModel
from app.schemas.user import AddressOut


# ── Checkout (guest + authenticated) ────────────────────────────


class CheckoutItemCreate(CamelModel):
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    quantity: Annotated[int, Field(ge=1)]
    size: Annotated[str, Field(min_length=1, max_length=10)]
    color: Annotated[str, Field(min_length=1, max_length=50)]

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class CheckoutRequest(CamelModel):
    """Matches the frontend checkout form exactly.
    Works for both guest and logged-in users."""

    items: Annotated[list[CheckoutItemCreate], Field(min_length=1)]
    email: EmailStr
    phone: Annotated[
        str, Field(min_length=7, max_length=20, pattern=r"^[0-9+()\-\s]+$")
    ]
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    street: Annotated[str, Field(min_length=1, max_length=255)]
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    discount_code: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    notes: Annotated[str, Field(min_length=1, max_length=2000)] | None = None


# ── Legacy authenticated order (kept for backwards compat) ──────


class OrderItemCreate(CamelModel):
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    quantity: Annotated[int, Field(ge=1)]
    size: Annotated[str, Field(min_length=1, max_length=10)]
    color: Annotated[str, Field(min_length=1, max_length=50)]

    @field_validator("quantity")
    @classmethod
    def order_quantity_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class OrderCreate(CamelModel):
    items: Annotated[list[OrderItemCreate], Field(min_length=1)]
    address_id: str | None = None
    shipping_address: "AddressInline | None" = None
    discount_code: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    phone: (
        Annotated[str, Field(min_length=7, max_length=20, pattern=r"^[0-9+()\-\s]+$")]
        | None
    ) = None
    notes: Annotated[str, Field(min_length=1, max_length=2000)] | None = None


class AddressInline(CamelModel):
    label: Annotated[str, Field(min_length=1, max_length=50)]
    street: Annotated[str, Field(min_length=1, max_length=255)]
    city: Annotated[str, Field(min_length=1, max_length=100)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    postal_code: Annotated[str, Field(min_length=1, max_length=20)]
    country: Annotated[str, Field(min_length=1, max_length=100)] = "Pakistan"


# ── Output schemas ──────────────────────────────────────────────


class OrderItemOut(CamelModel):
    product: dict
    quantity: int
    size: str
    color: str


class OrderOut(CamelModel):
    id: str
    order_number: str
    items: list[OrderItemOut] = Field(default_factory=list)
    status: str
    subtotal: float
    shipping: float
    discount: float
    total: float
    shipping_address: dict
    payment_method: str
    tracking_number: str | None = None
    created_at: datetime
    updated_at: datetime


class OrderStatusUpdate(CamelModel):
    status: Annotated[str, Field(min_length=1, max_length=20)]
    tracking_number: Annotated[str, Field(min_length=1, max_length=100)] | None = None


# Rebuild for forward ref
OrderCreate.model_rebuild()
