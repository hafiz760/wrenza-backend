import pytest


@pytest.mark.asyncio
async def test_indexability_survives_create_update_and_public_reads(client, admin_headers):
    created = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Indexability Wallet", "description": "Leather wallet", "price": 2500, "stock": 2, "isIndexable": False},
    )
    assert created.status_code == 200, created.text
    product = created.json()
    assert product["isIndexable"] is False

    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.json()["isIndexable"] is False
    listing = await client.get("/api/v1/products")
    assert next(p for p in listing.json()["items"] if p["id"] == product["id"])["isIndexable"] is False

    changed = await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={"isIndexable": True},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["isIndexable"] is True
    assert (await client.get(f"/api/v1/products/{product['slug']}")).json()["isIndexable"] is True
