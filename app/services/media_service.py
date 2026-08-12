"""Where a media URL is referenced.

Backs the dashboard's rename guard. Renaming a file on ImageKit changes its
URL, and every image reference in this database is a stored URL string rather
than a file id — so renaming something still in use leaves a dead link that
nothing reports. The dashboard asks here first and refuses the rename when
anything comes back.
"""

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Order, OrderItem
from app.db.models.product import Category, Collection, Product, ProductImage
from app.db.models.promotion import Banner
from app.db.models.review import Testimonial

# Backslash rather than the SQL default: LIKE's own escape character has to be
# stated explicitly for both SQLite and Postgres to agree on it.
_ESCAPE = "\\"


def _normalize(url: str) -> str:
    """Drop any ImageKit transformation query, leaving the bare file URL.

    A gallery may store `…/wallet.webp?tr=w-264` while the media library knows
    the file only as `…/wallet.webp`. Both name the same file.
    """
    return url.split("?", 1)[0]


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards in a value being matched literally.

    `_` matches any single character, and uploaded filenames are full of them
    — `IMG_5721.webp` would otherwise also match `IMGX5721.webp`. Backslash is
    escaped first so it cannot double-escape the wildcards added after it.
    """
    return (
        value.replace(_ESCAPE, _ESCAPE * 2)
        .replace("%", f"{_ESCAPE}%")
        .replace("_", f"{_ESCAPE}_")
    )


def _matches(column, url: str):
    """A column holding this exact URL, with or without a transformation query."""
    return or_(
        column == url,
        column.like(f"{_escape_like(url)}?%", escape=_ESCAPE),
    )


async def find_url_references(db: AsyncSession, url: str) -> list[dict]:
    """Everything referencing `url`, as `{type, name}` rows.

    An empty list means the file is safe to rename. Order references are
    permanent: an image can be detached from a product, but never from a
    completed order.
    """
    url = _normalize(url)
    if not url:
        return []

    references: list[dict] = []

    # Social share card. A product has no featured-image column — the feature
    # image is a `product_images` row flagged `is_featured`, so the gallery
    # scan below already covers it.
    products = await db.scalars(
        select(Product).where(_matches(Product.og_image, url))
    )
    references.extend({"type": "product", "name": p.name} for p in products)

    # Galleries. One table serves both product-level and variation images, and
    # both hang off a product, so the join names either the same way.
    gallery = await db.execute(
        select(Product.name, ProductImage.variation_id)
        .join(Product, Product.id == ProductImage.product_id)
        .where(_matches(ProductImage.url, url))
    )
    for name, variation_id in gallery.all():
        references.append(
            {
                "type": "variation" if variation_id else "product",
                "name": name,
            }
        )

    collections = await db.scalars(
        select(Collection).where(_matches(Collection.image, url))
    )
    references.extend({"type": "collection", "name": c.name} for c in collections)

    categories = await db.scalars(
        select(Category).where(_matches(Category.image_url, url))
    )
    references.extend({"type": "category", "name": c.name} for c in categories)

    banners = await db.scalars(select(Banner).where(_matches(Banner.image_url, url)))
    references.extend({"type": "banner", "name": b.title} for b in banners)

    testimonials = await db.scalars(
        select(Testimonial).where(_matches(Testimonial.avatar, url))
    )
    references.extend({"type": "testimonial", "name": t.name} for t in testimonials)

    # Order snapshots are JSON, so this is a substring match over the serialized
    # column rather than a comparison against a known key — the URL can sit at
    # several depths depending on what was bought.
    orders = await db.execute(
        select(Order.order_number)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            cast(OrderItem.product_snapshot, String).like(
                f"%{_escape_like(url)}%", escape=_ESCAPE
            )
        )
        .distinct()
    )
    references.extend(
        {"type": "order", "name": f"Order #{number}"} for number in orders.scalars()
    )

    return references
