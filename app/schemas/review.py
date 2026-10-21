from datetime import datetime
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import CamelModel


class ReviewCreate(CamelModel):
    """A review from either a signed-in customer or a guest.

    `name` and `email` are required for a guest and ignored for a signed-in
    customer, whose details come from the account instead — so a display name
    on a signed-in review cannot be forged.
    """

    product_id: Annotated[str, Field(min_length=1, max_length=36)]
    rating: Annotated[int, Field(ge=1, le=5)]
    comment: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    images: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=3
    )
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    email: EmailStr | None = None

    @field_validator("images")
    @classmethod
    def validate_image_urls(cls, images: list[str]) -> list[str]:
        for image in images:
            parsed = urlsplit(image)
            path_segments = [segment for segment in parsed.path.split("/") if segment]
            if (
                parsed.scheme != "https"
                or parsed.hostname != "ik.imagekit.io"
                or len(path_segments) < 3
                or path_segments[1] != "reviews"
            ):
                raise ValueError("Review images must be HTTPS ImageKit URLs")
        return images


class ReviewOut(CamelModel):
    """One approved review, as the storefront sees it.

    `user_id` is null for a guest. The guest's email is deliberately absent —
    publishing it on a public product page would leak it to scrapers.
    """

    id: str
    user_id: str | None = None
    user_name: str
    rating: int
    comment: str | None = None
    images: list[str] = Field(default_factory=list)
    created_at: datetime


class ReviewSummary(CamelModel):
    """Aggregates over the approved reviews, for the star histogram.

    Computed from the same rows the list returns rather than read from
    `products.rating`, so the summary and the visible reviews cannot disagree.
    """

    average: float
    total: int
    # Keyed "1".."5" — JSON object keys are strings, so this survives the
    # round-trip to the storefront unchanged.
    distribution: dict[str, int] = Field(
        default_factory=lambda: {str(star): 0 for star in range(1, 6)}
    )


class ProductReviewsOut(CamelModel):
    items: list[ReviewOut] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    total_pages: int
    summary: ReviewSummary


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
    image: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    is_verified_buyer: bool | None = None
    is_active: bool | None = None

