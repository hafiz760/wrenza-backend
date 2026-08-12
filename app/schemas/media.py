from app.schemas.common import CamelModel


class MediaReference(CamelModel):
    """One thing pointing at an image.

    `type` is `product`, `variation`, `collection`, `category`, `banner`,
    `testimonial` or `order`. Order references cannot be cleared — the
    dashboard presents those as permanent.
    """

    type: str
    name: str


class MediaUsageOut(CamelModel):
    in_use: bool
    references: list[MediaReference]
