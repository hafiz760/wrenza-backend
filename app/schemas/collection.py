from datetime import datetime
from typing import Annotated

from pydantic import Field

from app.schemas.common import CamelModel


class CollectionOut(CamelModel):
    id: str
    slug: str
    name: str
    tagline: str | None = None
    description: str | None = None
    image: str | None = None
    product_ids: list[str] = Field(default_factory=list)
    season: str | None = None
    year: int | None = None
    is_featured: bool
    created_at: datetime


class CollectionCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    tagline: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    image: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    product_ids: list[Annotated[str, Field(min_length=1)]] = Field(default_factory=list)
    season: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    year: Annotated[int, Field(ge=1900, le=2100)] | None = None
    is_featured: bool = False


class CollectionUpdate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    tagline: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    image: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    product_ids: list[Annotated[str, Field(min_length=1)]] | None = None
    season: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    year: Annotated[int, Field(ge=1900, le=2100)] | None = None
    is_featured: bool | None = None
    is_active: bool | None = None
