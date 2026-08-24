"""Clearing a product's featured image through `PUT /admin/products/{id}`.

The dashboard clears it by sending `featuredImage: null` in the update
payload. `ProductUpdate.model_dump(exclude_unset=True)` keeps that key —
`null` is what was explicitly sent, not an omitted field — so the service saw
`update_data["featured_image"] = None`.

The old code popped with a `None` default and tested `is not None`, which
cannot distinguish "field omitted, leave it alone" from "field sent as null,
clear it": both looked identical once popped. So a clear silently did nothing
and the old flagged ProductImage row stayed in the database, still coming
back as `featuredImage` on every read.
"""

import pytest


async def _product(client, admin_headers, **extra):
    body = {
        "name": "Curve Wallet",
        "description": "Leather.",
        "price": 2650,
        "stock": 10,
        "featuredImage": {"url": "https://cdn.example.com/featured.webp", "alt": "F"},
    }
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_clearing_the_featured_image_removes_it(client, admin_headers):
    product = await _product(client, admin_headers)
    assert product["featuredImage"]["url"] == "https://cdn.example.com/featured.webp"

    response = await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={"featuredImage": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"] is None


@pytest.mark.asyncio
async def test_cleared_featured_image_stays_cleared_on_read(
    client, admin_headers
):
    """The bug as the admin actually saw it: gone from the update response,
    but still there the next time the product loads."""
    product = await _product(client, admin_headers)
    await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={"featuredImage": None},
    )

    response = await client.get(f"/api/v1/products/{product['slug']}")
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"] is None


@pytest.mark.asyncio
async def test_omitting_featured_image_leaves_it_alone(client, admin_headers):
    """An update that never mentions the field must not be read as clearing
    it — only an explicit null does that."""
    product = await _product(client, admin_headers)

    response = await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={"name": "Curve Wallet Renamed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"]["url"] == (
        "https://cdn.example.com/featured.webp"
    )


@pytest.mark.asyncio
async def test_featured_image_can_be_replaced(client, admin_headers):
    product = await _product(client, admin_headers)

    response = await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={
            "featuredImage": {
                "url": "https://cdn.example.com/new.webp",
                "alt": "New",
            }
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"]["url"] == "https://cdn.example.com/new.webp"
