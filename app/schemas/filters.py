# pyrefly: ignore [missing-import]
from pydantic import Field

from app.schemas.common import CamelModel


class FilterTermOut(CamelModel):
    id: str
    value: str
    slug: str
    # Presentation payload, e.g. {"hex": "#000000"} for a colour swatch
    meta: dict = Field(default_factory=dict)
    # Active products offering this term. Zero-count terms are omitted from the
    # response entirely — an option that returns nothing is a dead end.
    product_count: int


class FilterAttributeOut(CamelModel):
    id: str
    name: str
    slug: str
    terms: list[FilterTermOut] = Field(default_factory=list)


class PriceBoundsOut(CamelModel):
    min: float
    max: float


class ProductFiltersOut(CamelModel):
    """Everything the catalog filter sidebar needs, in one request.

    Counts are computed with the same join `?attrs=` filters on, so a term
    advertising N products returns exactly N when selected.
    """

    attributes: list[FilterAttributeOut] = Field(default_factory=list)
    price: PriceBoundsOut
