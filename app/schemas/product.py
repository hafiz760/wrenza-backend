from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

# pyrefly: ignore [missing-import]
from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel

# Re-exported: these used to live here, and admin routers still import them
# from this module. They moved to break the product ↔ variation import cycle.
from app.schemas.faq import FaqOut
from app.schemas.image import ProductImageCreate, ProductImageOut
from app.schemas.variation import ProductAttributeOut, VariationOut
from app.utils.html import sanitize_html, to_plain_text

__all__ = [
    "ProductImageCreate",
    "ProductImageOut",
]


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
    meta_title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    is_indexable: bool
    updated_at: datetime
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
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    canonical_url: Annotated[str, Field(max_length=500)] | None = None
    is_indexable: bool = True
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
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    canonical_url: Annotated[str, Field(max_length=500)] | None = None
    is_indexable: bool | None = None
    parent_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("parent_id", mode="before")
    @classmethod
    def normalize_parent_id(cls, value):
        if value in ("", "#", "null", "None"):
            return None
        return value


class PriceRange(CamelModel):
    """Min/max across a variable product's active variations."""

    min: float
    max: float


class APlusImage(CamelModel):
    """One composition of the A+ section.

    `width`/`height` come from ImageKit at upload. They default to 0 rather
    than being required because older uploads did not report them, but an A+
    image is tall enough that a missing size means a very visible jump when it
    loads — the dashboard sends them.
    """

    url: Annotated[str, Field(min_length=1, max_length=500)]
    width: int = 0
    height: int = 0


class APlusContent(CamelModel):
    """Optional marketing image below the product tabs.

    Two images, not one scaled: the text is part of the picture, so a desktop
    composition shrunk to a phone is unreadable.
    """

    desktop: APlusImage | None = None
    mobile: APlusImage | None = None
    alt: Annotated[str, Field(max_length=255)] | None = None

    @field_validator("alt", mode="after")
    @classmethod
    def plain_text_only(cls, value: str | None) -> str | None:
        """Alt text is an attribute, not markup."""
        return to_plain_text(value) or None if value else None

    @model_validator(mode="after")
    def require_alt_with_an_image(self) -> "APlusContent":
        """Everything in the image is invisible without it.

        The copy is baked into the pixels, so alt text is the only thing a
        search engine or a screen reader ever gets from this section. An image
        without it is a silent hole in the page.
        """
        if (self.desktop or self.mobile) and not self.alt:
            raise ValueError("alt text is required when an A+ image is set")
        return self


class ProductOut(CamelModel):
    """Full product detail — matches frontend Product type exactly."""

    id: str
    slug: str
    name: str
    sku: str | None = None
    canonical_url: str | None = None
    og_image: str | None = None
    short_description: str | None = None
    description: str
    kind: Literal["simple", "variable"] = "simple"
    price: float
    price_range: PriceRange | None = None
    compare_at_price: float | None = None
    currency: str
    featured_image: ProductImageOut | None = None
    images: list[ProductImageOut] = Field(default_factory=list)
    category: str | None = None
    product_type: str | None = None
    a_plus_content: APlusContent | None = None
    dimensions: ProductDimensions = Field(default_factory=ProductDimensions)
    care_instructions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    rating: float
    review_count: int
    stock: int
    is_featured: bool
    is_new_arrival: bool
    is_indexable: bool
    created_at: datetime
    updated_at: datetime

    # `price`/`price_range`/`stock` above are aggregates over these. A variable
    # product needs the variations themselves for the storefront to render an
    # option picker and to send a `variationId` at checkout.
    attributes: list[ProductAttributeOut] = Field(default_factory=list)
    variations: list[VariationOut] = Field(default_factory=list)

    # Rendered on the page and emitted as FAQPage structured data. Both come
    # from here so the markup can never quote something the page does not show.
    faqs: list[FaqOut] = Field(default_factory=list)


class ProductListOut(CamelModel):
    """Lighter product for listing pages."""

    id: str
    slug: str
    name: str
    price: float
    price_range: PriceRange | None = None
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
    is_indexable: bool
    updated_at: datetime
    # Lets a card tell "add to cart" from "choose options" without fetching the
    # detail payload — a variable product needs a variation before it can sell.
    kind: Literal["simple", "variable"] = "simple"
    # Colour terms the product offers, for the swatch row on a card. Loaded in
    # one grouped query per page, not per product.
    swatches: list["ProductSwatchOut"] = Field(default_factory=list)


class ProductSwatchOut(CamelModel):
    """A colour option shown on a product card."""

    term_id: str
    value: str
    slug: str
    hex: str


ProductListOut.model_rebuild()


class ProductCreate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    short_description: Annotated[str, Field(max_length=2000)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=20000)]
    kind: Literal["simple", "variable"] = "simple"
    price: Annotated[float, Field(ge=0)]
    compare_at_price: Annotated[float, Field(ge=0)] | None = None
    category_id: str | None = None
    product_type: (
        Literal["wallet", "bag", "belt", "card-holder", "accessory"] | None
    ) = None
    a_plus_content: APlusContent | None = None
    dimensions: ProductDimensions = Field(default_factory=ProductDimensions)
    care_instructions: list[Annotated[str, Field(min_length=1, max_length=200)]] = (
        Field(default_factory=list)
    )
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] = Field(
        default_factory=list
    )
    stock: Annotated[int, Field(ge=0)] = 0
    is_featured: bool = False
    is_new_arrival: bool = False
    is_indexable: bool = True
    sku: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    canonical_url: Annotated[str, Field(max_length=500)] | None = None
    og_image: Annotated[str, Field(max_length=500)] | None = None
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    featured_image: ProductImageCreate | None = Field(
        default=None, description="Hero image. Kept out of the gallery."
    )
    images: list[ProductImageCreate] = Field(
        default_factory=list, description="Gallery images, excluding the feature image."
    )

    @field_validator("description", "short_description", mode="after")
    @classmethod
    def sanitize_rich_text(cls, value: str | None) -> str | None:
        """Strip anything executable before it reaches a storefront page."""
        return sanitize_html(value)



class ProductUpdate(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    slug: (
        Annotated[
            str,
            Field(min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
        ]
        | None
    ) = None
    short_description: Annotated[str, Field(max_length=2000)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=20000)] | None = None
    kind: Literal["simple", "variable"] | None = None
    price: Annotated[float, Field(ge=0)] | None = None
    compare_at_price: Annotated[float, Field(ge=0)] | None = None
    category_id: str | None = None
    product_type: (
        Literal["wallet", "bag", "belt", "card-holder", "accessory"] | None
    ) = None
    a_plus_content: APlusContent | None = None
    dimensions: ProductDimensions | None = None
    care_instructions: (
        list[Annotated[str, Field(min_length=1, max_length=200)]] | None
    ) = None
    tags: list[Annotated[str, Field(min_length=1, max_length=50)]] | None = None
    stock: Annotated[int, Field(ge=0)] | None = None
    is_featured: bool | None = None
    is_new_arrival: bool | None = None
    is_active: bool | None = None
    is_indexable: bool | None = None
    sku: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    canonical_url: Annotated[str, Field(max_length=500)] | None = None
    og_image: Annotated[str, Field(max_length=500)] | None = None
    meta_title: Annotated[str, Field(min_length=1, max_length=255)] | None = None
    meta_description: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    featured_image: ProductImageCreate | None = Field(
        default=None, description="Replaces the existing feature image when supplied."
    )
    images: list[ProductImageCreate] | None = Field(
        default=None,
        description=(
            "Full gallery in display order, excluding the feature image. "
            "Omit to leave the gallery untouched; send [] to clear it."
        ),
    )

    @field_validator("description", "short_description", mode="after")
    @classmethod
    def sanitize_rich_text(cls, value: str | None) -> str | None:
        """Strip anything executable before it reaches a storefront page."""
        return sanitize_html(value)



# Allow forward references
CategoryOut.model_rebuild()
