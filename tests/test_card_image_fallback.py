"""When a variable product has no product-level image, use a variation's.

Photographing per colour and never duplicating a shot onto the product level
is a normal workflow — the detail page already handles it, because it resolves
a variation of its own on load. But every other place a product appears —
shop grid, homepage, related products, search, wishlist, cart — reads
`featuredImage` with no variation in play at all. Without this fallback those
all rendered a blank placeholder for a fully-photographed product.
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def setup(client, admin_headers):
    """A variable product with Colour(Blue, Tan, Brown), no attributes fixture
    reused from test_variations.py so this file stays self-contained."""
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Curve Wallet",
            "description": "Full grain leather.",
            "kind": "variable",
            "price": 2650,
        },
    )
    product_id = product.json()["id"]
    slug = product.json()["slug"]

    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Colour"}
    )
    attr_id = attr.json()["id"]
    term_ids = []
    for value in ("Blue", "Tan", "Brown"):
        term = await client.post(
            f"/api/v1/admin/attributes/{attr_id}/terms",
            headers=admin_headers,
            json={"value": value},
        )
        term_ids.append(term.json()["id"])

    await client.put(
        f"/api/v1/admin/products/{product_id}/attributes",
        headers=admin_headers,
        json={"attributes": [{"attributeId": attr_id, "termIds": term_ids}]},
    )

    generated = await client.post(
        f"/api/v1/admin/products/{product_id}/variations/generate",
        headers=admin_headers,
    )
    variations = generated.json()
    return {"product_id": product_id, "slug": slug, "variations": variations}


async def _add_image(client, admin_headers, product_id, variation_id, url):
    response = await client.post(
        f"/api/v1/admin/products/{product_id}/variations/{variation_id}/images",
        headers=admin_headers,
        json={"url": url, "alt": "colour shot"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_card_falls_back_to_first_variation_image(
    client, admin_headers, setup
):
    """No product-level photo at all — the first variation's image is used,
    matching the order the admin sees on the Variations tab."""
    first_variation = setup["variations"][0]
    await _add_image(
        client,
        admin_headers,
        setup["product_id"],
        first_variation["id"],
        "https://cdn.example.com/blue-1.webp",
    )

    response = await client.get(f"/api/v1/products/{setup['slug']}")
    assert response.status_code == 200, response.text
    assert (
        response.json()["featuredImage"]["url"]
        == "https://cdn.example.com/blue-1.webp"
    )


@pytest.mark.asyncio
async def test_product_level_image_still_wins(client, admin_headers, setup):
    """The fallback only applies when nothing was set at the product level —
    it must not override a featured image the admin actually chose."""
    first_variation = setup["variations"][0]
    await _add_image(
        client,
        admin_headers,
        setup["product_id"],
        first_variation["id"],
        "https://cdn.example.com/blue-1.webp",
    )
    await client.put(
        f"/api/v1/admin/products/{setup['product_id']}",
        headers=admin_headers,
        json={
            "featuredImage": {
                "url": "https://cdn.example.com/hero.webp",
                "alt": "Hero",
            }
        },
    )

    response = await client.get(f"/api/v1/products/{setup['slug']}")
    assert response.json()["featuredImage"]["url"] == "https://cdn.example.com/hero.webp"


@pytest.mark.asyncio
async def test_inactive_variation_is_skipped(client, admin_headers, setup):
    """A deactivated variation's photo must not represent the product."""
    variations = setup["variations"]
    await _add_image(
        client, admin_headers, setup["product_id"], variations[0]["id"], "https://cdn.example.com/blue-1.webp"
    )
    await _add_image(
        client, admin_headers, setup["product_id"], variations[1]["id"], "https://cdn.example.com/tan-1.webp"
    )
    await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=admin_headers,
        json={"variations": [{"id": variations[0]["id"], "isActive": False}]},
    )

    response = await client.get(f"/api/v1/products/{setup['slug']}")
    assert (
        response.json()["featuredImage"]["url"]
        == "https://cdn.example.com/tan-1.webp"
    )


@pytest.mark.asyncio
async def test_no_images_anywhere_is_still_null(client, admin_headers, setup):
    """No product image and no variation image — a placeholder, not a crash."""
    response = await client.get(f"/api/v1/products/{setup['slug']}")
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"] is None


@pytest.mark.asyncio
async def test_fallback_also_applies_in_listings(client, admin_headers, setup):
    """The shop grid and homepage read the list endpoint, not the detail one —
    the same fallback has to hold there too."""
    first_variation = setup["variations"][0]
    await _add_image(
        client,
        admin_headers,
        setup["product_id"],
        first_variation["id"],
        "https://cdn.example.com/blue-1.webp",
    )

    response = await client.get("/api/v1/products")
    assert response.status_code == 200, response.text
    item = next(p for p in response.json()["items"] if p["slug"] == setup["slug"])
    assert item["featuredImage"]["url"] == "https://cdn.example.com/blue-1.webp"
