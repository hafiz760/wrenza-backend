from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.schemas.common import CamelModel


class ReviewCreate(CamelModel):
    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    rating: Annotated[int, Field(ge=1, le=5)]
    comment: Annotated[str, Field(min_length=1, max_length=2000)] | None = None


class ReviewOut(CamelModel):
    id: str
    user_id: str
    user_name: str
    rating: int
    comment: str | None = None
    created_at: datetime


class TestimonialOut(CamelModel):
    id: str
    name: str
    location: str | None = None
    avatar: str | None = None
    comment: str
    rating: int


class TestimonialCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    location: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    avatar: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    comment: Annotated[str, Field(min_length=1, max_length=2000)]
    rating: Annotated[int, Field(ge=1, le=5)]
