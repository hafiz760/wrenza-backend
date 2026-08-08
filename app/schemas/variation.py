from typing import Annotated, Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.image import ProductImageCreate, ProductImageOut


class VariationValueOut(CamelModel):
    """One (attribute, term) pair, resolved to names for display."""

    attribute_id: str
    attribute_name: str
    attribute_slug: str
    term_id: str
    term_value: str
    term_slug: str
    # Presentation data set by the admin, e.g. {"hex": "#000000"}. Without it
    # the storefront cannot render a colour attribute as swatches.
    meta: dict = Field(default_factory=dict)


class VariationOut(CamelModel):
    id: str
    sku: str | None = None
    gtin: str | None = None
    price: float
    compare_at_price: float | None = None
    stock: int
    is_active: bool
    position: int
    values: list[VariationValueOut] = Field(default_factory=list)
    featured_image: ProductImageOut | None = None
    images: list[ProductImageOut] = Field(default_factory=list)


class ProductAttributeAssign(CamelModel):
    attribute_id: str
    term_ids: Annotated[list[str], Field(min_length=1)]
    used_for_variations: bool = True
    position: Annotated[int, Field(ge=0)] = 0


class ProductAttributesUpdate(CamelModel):
    """Replaces the product's attribute selection wholesale."""

    attributes: list[ProductAttributeAssign] = Field(default_factory=list)


class ProductAttributeOut(CamelModel):
    attribute_id: str
    attribute_name: str
    attribute_slug: str
    used_for_variations: bool
    position: int
    terms: list[VariationValueOut] = Field(default_factory=list)


class VariationUpdate(CamelModel):
    """One row of a bulk variation edit."""

    id: str
    sku: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    gtin: Annotated[str, Field(min_length=1, max_length=50)] | None = None
    price: Annotated[float, Field(ge=0)] | None = None
    compare_at_price: Annotated[float, Field(ge=0)] | None = None
    stock: Annotated[int, Field(ge=0)] | None = None
    is_active: bool | None = None
    position: Annotated[int, Field(ge=0)] | None = None


class VariationBulkUpdate(CamelModel):
    variations: Annotated[list[VariationUpdate], Field(min_length=1)]


class VariationImageCreate(ProductImageCreate):
    is_featured: bool = False


class ProductKindUpdate(CamelModel):
    kind: Literal["simple", "variable"]
