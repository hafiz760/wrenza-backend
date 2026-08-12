"""The rename guard: what is a media URL still attached to?

Renaming a file on ImageKit changes its URL, and every image reference in this
database is a stored URL string rather than a file id. Renaming something still
in use leaves a dead link that nothing reports — the storefront and the admin
panel both render the 404. The dashboard asks this endpoint first and refuses
the rename when anything comes back.

`test_underscore_is_not_a_wildcard` is the one to keep: uploaded filenames are
full of underscores, and `_` is a single-character wildcard in SQL LIKE.
Without an explicit ESCAPE clause the order scan reports references that do not
exist, and every rename looks blocked.
"""

import pytest
from sqlalchemy import select

from app.db.models.order import Order, OrderItem
from app.db.models.product import Category, Collection, Product, ProductImage
from app.db.models.promotion import Banner
from app.db.models.review import Testimonial
from tests.conftest import TestingSessionLocal

URL = "https://ik.imagekit.io/wrenza/products/IMG_5721.webp"
OTHER = "https://ik.imagekit.io/wrenza/products/unrelated.webp"


async def _usage(client, admin_headers, url=URL):
    response = await client.get(
        "/api/v1/admin/media/usage", headers=admin_headers, params={"url": url}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _types(payload) -> set[str]:
    return {ref["type"] for ref in payload["references"]}


async def _product(name="Blue Leather Wallet", image_url=None, og_image=None):
    """A minimal product row, optionally with a featured gallery image.

    Created directly: the admin create endpoint demands a full payload, and
    these tests only care about the URL columns. `image_url` becomes a featured
    `product_images` row, because a product has no image column of its own.
    """
    async with TestingSessionLocal() as db:
        product = Product(
            name=name,
            slug=name.lower().replace(" ", "-"),
            description="",
            price=1000,
            og_image=og_image,
        )
        db.add(product)
        await db.flush()
        if image_url:
            db.add(
                ProductImage(
                    product_id=product.id, url=image_url, alt="", is_featured=True
                )
            )
        await db.commit()
        await db.refresh(product)
        return product.id


async def _order(snapshot: dict, order_number="1042"):
    async with TestingSessionLocal() as db:
        order = Order(
            order_number=order_number,
            subtotal=1000,
            total=1000,
            shipping_address={"city": "Lahore"},
        )
        db.add(order)
        await db.flush()
        db.add(
            OrderItem(
                order_id=order.id,
                product_snapshot=snapshot,
                quantity=1,
                unit_price=1000,
            )
        )
        await db.commit()


# ── Nothing referencing it ──────────────────────────────────────


@pytest.mark.asyncio
async def test_unused_image_is_renameable(client, admin_headers):
    """The common case: uploaded, not yet attached, safe to rename."""
    await _product(image_url=OTHER)

    payload = await _usage(client, admin_headers)
    assert payload["inUse"] is False
    assert payload["references"] == []


@pytest.mark.asyncio
async def test_response_is_camel_case(client, admin_headers):
    """`in_use` reaching the dashboard as snake_case reads as falsy, which
    would let every rename through."""
    payload = await _usage(client, admin_headers)
    assert "inUse" in payload
    assert "in_use" not in payload


# ── Each kind of reference ──────────────────────────────────────


@pytest.mark.asyncio
async def test_product_featured_image_blocks(client, admin_headers):
    """The feature image is a flagged `product_images` row, not a column."""
    await _product(image_url=URL)

    payload = await _usage(client, admin_headers)
    assert payload["inUse"] is True
    assert _types(payload) == {"product"}
    assert payload["references"][0]["name"] == "Blue Leather Wallet"


@pytest.mark.asyncio
async def test_product_og_image_blocks(client, admin_headers):
    """The social share card is a separate column and was easy to miss."""
    await _product(og_image=URL)

    assert (await _usage(client, admin_headers))["inUse"] is True


@pytest.mark.asyncio
async def test_product_gallery_blocks(client, admin_headers):
    product_id = await _product()
    async with TestingSessionLocal() as db:
        db.add(ProductImage(product_id=product_id, url=URL, alt=""))
        await db.commit()

    payload = await _usage(client, admin_headers)
    assert _types(payload) == {"product"}


@pytest.mark.asyncio
async def test_transformed_url_still_matches(client, admin_headers):
    """A gallery may store the URL with an ImageKit transformation appended.
    It is the same file, and renaming it breaks that reference too."""
    product_id = await _product()
    async with TestingSessionLocal() as db:
        db.add(ProductImage(product_id=product_id, url=f"{URL}?tr=w-264", alt=""))
        await db.commit()

    assert (await _usage(client, admin_headers))["inUse"] is True


@pytest.mark.asyncio
async def test_collection_category_banner_testimonial_block(client, admin_headers):
    async with TestingSessionLocal() as db:
        db.add(Collection(name="Autumn Edit", slug="autumn-edit", image=URL))
        db.add(Category(name="Wallets", slug="wallets", image_url=URL))
        db.add(Banner(title="Eid Sale", image_url=URL))
        db.add(Testimonial(name="Ayesha", avatar=URL, comment="Lovely", rating=5))
        await db.commit()

    payload = await _usage(client, admin_headers)
    assert _types(payload) == {"collection", "category", "banner", "testimonial"}


@pytest.mark.asyncio
async def test_past_order_blocks_permanently(client, admin_headers):
    """An image can be detached from a product but never from a completed
    order, so this reference can never be cleared."""
    await _order({"name": "Blue Leather Wallet", "imageUrl": URL})

    payload = await _usage(client, admin_headers)
    assert payload["inUse"] is True
    assert _types(payload) == {"order"}
    assert payload["references"][0]["name"] == "Order #1042"


@pytest.mark.asyncio
async def test_order_reference_survives_detaching_from_product(
    client, admin_headers
):
    """The sequence that motivated scanning orders: attach, sell, detach.
    The product no longer points at the image, but the snapshot still does."""
    await _order({"name": "Blue Leather Wallet", "imageUrl": URL})
    await _product(image_url=None)

    assert _types(await _usage(client, admin_headers)) == {"order"}


# ── The escaping bug ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_underscore_is_not_a_wildcard(client, admin_headers):
    """`IMG_5721.webp` must not match `IMGX5721.webp`.

    The order scan matches the serialized JSON with LIKE, where `_` means "any
    single character". Without an ESCAPE clause this reports a reference to an
    unrelated file and blocks a rename that was perfectly safe.
    """
    await _order({"name": "Something Else", "imageUrl": URL.replace("IMG_", "IMGX")})

    payload = await _usage(client, admin_headers)
    assert payload["inUse"] is False, payload["references"]


@pytest.mark.asyncio
async def test_percent_is_not_a_wildcard(client, admin_headers):
    """Same class of bug for `%`, which matches any run of characters.

    Unescaped, `a%b.webp` matches the unrelated `aXXXb.webp` stored below.
    """
    await _order({"imageUrl": "https://ik.imagekit.io/wrenza/products/aXXXb.webp"})

    payload = await _usage(
        client,
        admin_headers,
        url="https://ik.imagekit.io/wrenza/products/a%b.webp",
    )
    assert payload["inUse"] is False, payload["references"]


# ── Auth ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_usage_requires_admin(client, auth_headers):
    """A customer token must not be able to enumerate the catalogue this way."""
    response = await client.get(
        "/api/v1/admin/media/usage", headers=auth_headers, params={"url": URL}
    )
    assert response.status_code in (401, 403), response.text
