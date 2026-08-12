"""`productType` must survive a round trip through the API.

The field was stored on create and accepted on update, but neither output
mapper set it — so `ProductOut` fell back to its `None` default and every
response reported `productType: null` no matter what the row held.

That read bug caused a write bug. The dashboard loads the product into its
edit form, sees null, and sends null back on the next save, erasing a value
that was previously correct. Same shape as the SEO fields that were missing
from the mappers in 049e7e4.
"""

import pytest


async def _create(client, admin_headers, **extra):
    body = {
        "name": "Curve Wallet",
        "description": "A wallet.",
        "price": 2650,
        "stock": 10,
    }
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_product_type_returned_on_create(client, admin_headers):
    product = await _create(client, admin_headers, productType="card-holder")
    assert product["productType"] == "card-holder"


@pytest.mark.asyncio
async def test_product_type_returned_on_read(client, admin_headers):
    """The bug: stored correctly, reported as null."""
    created = await _create(client, admin_headers, productType="card-holder")

    response = await client.get(f"/api/v1/products/{created['slug']}")
    assert response.status_code == 200, response.text
    assert response.json()["productType"] == "card-holder"


@pytest.mark.asyncio
async def test_product_type_survives_an_unrelated_update(client, admin_headers):
    """Editing another field must not clear it.

    This is what the dashboard does on every save, and what silently emptied
    the field in production.
    """
    created = await _create(client, admin_headers, productType="wallet")

    response = await client.put(
        f"/api/v1/admin/products/{created['id']}",
        headers=admin_headers,
        json={"name": "Curve Wallet Renamed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["productType"] == "wallet"


@pytest.mark.asyncio
async def test_product_type_can_be_changed(client, admin_headers):
    created = await _create(client, admin_headers, productType="wallet")

    response = await client.put(
        f"/api/v1/admin/products/{created['id']}",
        headers=admin_headers,
        json={"productType": "belt"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["productType"] == "belt"
