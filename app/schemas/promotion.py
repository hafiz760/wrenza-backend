from datetime import date, datetime
from typing import Annotated

from pydantic import Field, model_validator

from app.schemas.common import CamelModel


class DiscountOut(CamelModel):
    id: str
    code: str
    percentage: int
    min_order_amount: float
    max_uses: int
    current_uses: int
    expires_at: datetime | None = None
    is_active: bool
    created_at: datetime


class DiscountCreate(CamelModel):
    code: Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9-]+$")]
    percentage: Annotated[int, Field(ge=1, le=100)]
    min_order_amount: Annotated[float, Field(ge=0)] = 0
    max_uses: Annotated[int, Field(ge=0)] = 0
    expires_at: datetime | None = None
    is_active: bool = True


class DiscountUpdate(CamelModel):
    code: (
        Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9-]+$")]
        | None
    ) = None
    percentage: Annotated[int, Field(ge=1, le=100)] | None = None
    min_order_amount: Annotated[float, Field(ge=0)] | None = None
    max_uses: Annotated[int, Field(ge=0)] | None = None
    expires_at: datetime | None = None
    is_active: bool | None = None


class BannerOut(CamelModel):
    id: str
    title: str
    image_url: str
    link: str | None = None
    position: int
    active_from: date | None = None
    active_to: date | None = None
    is_active: bool


class BannerCreate(CamelModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]
    image_url: Annotated[str, Field(min_length=1, max_length=500)]
    link: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    position: Annotated[int, Field(ge=0)] = 0
    active_from: date | None = None
    active_to: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_active_dates(self):
        if self.active_from and self.active_to and self.active_from > self.active_to:
            raise ValueError("active_from must be before or equal to active_to")
        return self


class BannerUpdate(CamelModel):
    title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    image_url: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    link: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    position: Annotated[int, Field(ge=0)] | None = None
    active_from: date | None = None
    active_to: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_active_dates(self):
        if self.active_from and self.active_to and self.active_from > self.active_to:
            raise ValueError("active_from must be before or equal to active_to")
        return self
