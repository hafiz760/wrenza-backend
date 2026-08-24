"""The optional A+ marketing image on a product.

The section is one tall image per breakpoint with its copy baked into the
pixels, so alt text is the only part a search engine or a screen reader can
read — which is why it is required as soon as an image is set rather than
being a nice-to-have field someone skips.

`test_a_plus_survives_an_unrelated_update` is the one to keep. The same class
of bug — a field stored on write but dropped by the output mapper — silently
erased `productType` in production: the dashboard loaded null, then saved null
back over a good value.
"""

import pytest

DESKTOP = {
    "url": "https://ik.imagekit.io/wrenza/a-plus-desktop.webp",
    "width": 1600,
    "height": 3354,
}
MOBILE = {
    "url": "https://ik.imagekit.io/wrenza/a-plus-mobile.webp",
    "width": 800,
    "height": 2400,
}
ALT = "Wrenza long leather wallet — card slots and stitching detail"


async def _create(client, admin_headers, **extra):
    body = {
        "name": "Long Wallet",
        "description": "Full grain leather.",
        "price": 4500,
        "stock": 5,
    }
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    return response


# ── Optional ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_without_a_plus_content_is_fine(client, admin_headers):
    """It is optional; every existing product has none."""
    created = await _create(client, admin_headers)
    assert created.status_code == 200, created.text
    assert created.json()["aPlusContent"] is None


# ── Round trip ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_plus_content_round_trips(client, admin_headers):
    created = await _create(
        client,
        admin_headers,
        aPlusContent={"desktop": DESKTOP, "mobile": MOBILE, "alt": ALT},
    )
    assert created.status_code == 200, created.text

    content = created.json()["aPlusContent"]
    assert content["desktop"]["url"] == DESKTOP["url"]
    assert content["desktop"]["width"] == 1600
    assert content["mobile"]["height"] == 2400
    assert content["alt"] == ALT


@pytest.mark.asyncio
async def test_a_plus_content_is_on_the_public_payload(client, admin_headers):
    created = await _create(
        client,
        admin_headers,
        aPlusContent={"desktop": DESKTOP, "alt": ALT},
    )
    slug = created.json()["slug"]

    response = await client.get(f"/api/v1/products/{slug}")
    assert response.status_code == 200, response.text
    assert response.json()["aPlusContent"]["desktop"]["url"] == DESKTOP["url"]


@pytest.mark.asyncio
async def test_a_plus_survives_an_unrelated_update(client, admin_headers):
    """Editing another field must not wipe it — the productType bug."""
    created = await _create(
        client,
        admin_headers,
        aPlusContent={"desktop": DESKTOP, "alt": ALT},
    )
    product_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/admin/products/{product_id}",
        headers=admin_headers,
        json={"name": "Long Wallet Renamed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["aPlusContent"]["desktop"]["url"] == DESKTOP["url"]


@pytest.mark.asyncio
async def test_a_plus_content_can_be_removed(client, admin_headers):
    created = await _create(
        client,
        admin_headers,
        aPlusContent={"desktop": DESKTOP, "alt": ALT},
    )
    product_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/admin/products/{product_id}",
        headers=admin_headers,
        json={"aPlusContent": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["aPlusContent"] is None


# ── Alt text ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_image_without_alt_text_is_rejected(client, admin_headers):
    response = await _create(
        client, admin_headers, aPlusContent={"desktop": DESKTOP}
    )
    assert response.status_code == 422, response.text
    assert "alt" in response.text.lower()


@pytest.mark.asyncio
async def test_alt_text_is_stripped_of_markup(client, admin_headers):
    """It lands in an HTML attribute; tags in there are never wanted."""
    created = await _create(
        client,
        admin_headers,
        aPlusContent={
            "desktop": DESKTOP,
            "alt": "<script>alert(1)</script>Blue wallet",
        },
    )
    assert created.status_code == 200, created.text
    assert "<script>" not in created.json()["aPlusContent"]["alt"]
