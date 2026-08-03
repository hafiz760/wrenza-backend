from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

# pyrefly: ignore [missing-import]
from pydantic import Field, field_validator

from app.schemas.common import CamelModel


class ProductImageOut(CamelModel):
    id: str
    url: Annotated[str, Field(min_length=1, max_length=500)]
    alt: Annotated[str, Field(max_length=255)]
    width: Annotated[int, Field(ge=0)]
    height: Annotated[int, Field(ge=0)]


class ProductImageCreate(CamelModel):
    url: Annotated[str, Field(min_length=1, max_length=500)]
    alt: Annotated[str, Field(max_length=255)] = ""
    width: Annotated[int, Field(ge=0)] = 0
    height: Annotated[int, Field(ge=0)] = 0
    position: Annotated[int, Field(ge=0)] = 0


class ProductSizeOut(CamelModel):
    label: Annotated[str, Field(min_length=1, max_length=50)]
    value: Annotated[str, Field(min_length=1, max_length=50)]
    in_stock: bool


class ProductColorOut(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=50)]
    hex: Annotated[str, Field(pattern=r"^#(?:[0-9a-fA-F]{3}){1,2}$")]
    in_stock: bool


class ProductDimensions(CamelModel):
    length_cm: Annotated[float, Field(ge=0)] | None = None
    width_cm: Annotated[float, Field(ge=0)] | None = None
    height_cm: Annotated[float, Field(ge=0)] | None = None


class CategoryOut(CamelModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    image_url: str | None = None
    children: list["CategoryOut"] = Field(default_factory=list)


class CategoryCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    image_url: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    parent_id: UUID | None = None

    @field_validator("parent_id", mode="before")
    @classmethod
    def normalize_parent_id(cls, value):
        if value in ("", "#", "null", "None"):
            return None
        return value


class CategoryUpdate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    image_url: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("parent_id", mode="before")
    @classmethod
    def normalize_parent_id(cls, value):
        if value in ("", "#", "null", "None"):
            return None
        return value


class ProductOut(CamelModel):
    """Full product detail — matches frontend Product type exactly."""

    id: str
    slug: str
    name: str
    description: str
    price: float
    compare_at_price: float | None = None
    currency: str
    featured_image: ProductImageOut | None = None
    images: list[ProductImageOut] = Field(default_factory=list)
    category: str | None = None
    product_type: str | None = None
    material: str | None = None
    leather_type: str | None = None
    dimensions: ProductDimensions = Field(default_factory=ProductDimensions)
    hardware_finish: str | None = None
    closure_type: str | None = None
    sizes: list[ProductSizeOut] = Field(default_factory=list)
    colors: list[ProductColorOut] = Field(default_factory=list)
    fabric: str | None = None
    care_instructions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    rating: float
    review_count: int
    stock: int
    is_featured: bool
    is_new_arrival: bool
    created_at: datetime
    updated_at: datetime


class ProductListOut(CamelModel):
    """Lighter product for listing pages."""

    id: str
    slug: str
    name: str
    price: float
    compare_at_price: float | None = None
    currency: str
    featured_image: ProductImageOut | None = None
    images: list[ProductImageOut] = Field(default_factory=list)
    category: str | None = None
    rating: float
    review_count: int
    stock: int
    is_featured: bool
    is_new_arrival: bool


class ProductCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    description: Annotated[str, Field(min_length=1, max_length=10000)]
    price: Annotated[float, Field(ge=0)]
    compare_at_price: Annotated[float, Field(ge=0)] | None = None
    category_id: str | None = None
    product_type: (
        Literal["wallet", "bag", "belt", "card-holder", "accessory"] | None
    ) = None
    material: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    leather_type: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    dimensions: ProductDimensions = Field(default_factory=ProductDimensions)
    hardware_finish: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    closure_type: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    fabric: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    gender: Literal["male", "female", "unisex"] | None = None
    sizes: list[ProductSizeOut] = Field(default_factory=list)
    colors: list[ProductColorOut] = Field(default_factory=list)
    care_instructions: list[Annotated[str, Field(min_length=1, max_length=200)]] = (
        Field(default_factory=list)
    )
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list
    )
    stock: Annotated[int, Field(ge=0)] = 0
    is_featured: bool = False
    is_new_arrival: bool = False
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    featured_image: ProductImageCreate | None = Field(
        default=None, description="Hero image. Kept out of the gallery."
    )
    images: list[ProductImageCreate] = Field(
        default_factory=list, description="Gallery images, excluding the feature image."
    )


class ProductUpdate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    price: Annotated[float, Field(ge=0)] | None = None
    compare_at_price: Annotated[float, Field(ge=0)] | None = None
    category_id: str | None = None
    product_type: (
        Literal["wallet", "bag", "belt", "card-holder", "accessory"] | None
    ) = None
    material: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    leather_type: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    dimensions: ProductDimensions | None = None
    hardware_finish: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    closure_type: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    fabric: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    gender: Literal["male", "female", "unisex"] | None = None
    sizes: list[ProductSizeOut] | None = None
    colors: list[ProductColorOut] | None = None
    care_instructions: (
        list[Annotated[str, Field(min_length=1, max_length=200)]] | None
    ) = None
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = None
    stock: Annotated[int, Field(ge=0)] | None = None
    is_featured: bool | None = None
    is_new_arrival: bool | None = None
    is_active: bool | None = None
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    featured_image: ProductImageCreate | None = Field(
        default=None, description="Replaces the existing feature image when supplied."
    )


# Allow forward references
CategoryOut.model_rebuild()
