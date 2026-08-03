from typing import Annotated

from pydantic import Field

from app.schemas.common import CamelModel

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class AttributeTermOut(CamelModel):
    id: str
    value: str
    slug: str
    meta: dict = Field(default_factory=dict)
    position: int


class AttributeOut(CamelModel):
    id: str
    name: str
    slug: str
    position: int
    is_filterable: bool
    terms: list[AttributeTermOut] = Field(default_factory=list)


class AttributeCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    slug: (
        Annotated[str, Field(min_length=1, max_length=120, pattern=SLUG_PATTERN)] | None
    ) = None
    position: Annotated[int, Field(ge=0)] = 0
    is_filterable: bool = True


class AttributeUpdate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    slug: (
        Annotated[str, Field(min_length=1, max_length=120, pattern=SLUG_PATTERN)] | None
    ) = None
    position: Annotated[int, Field(ge=0)] | None = None
    is_filterable: bool | None = None


class AttributeTermCreate(CamelModel):
    value: Annotated[str, Field(min_length=1, max_length=100)]
    slug: (
        Annotated[str, Field(min_length=1, max_length=120, pattern=SLUG_PATTERN)] | None
    ) = None
    meta: dict = Field(default_factory=dict)
    position: Annotated[int, Field(ge=0)] = 0


class AttributeTermUpdate(CamelModel):
    value: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    slug: (
        Annotated[str, Field(min_length=1, max_length=120, pattern=SLUG_PATTERN)] | None
    ) = None
    meta: dict | None = None
    position: Annotated[int, Field(ge=0)] | None = None
