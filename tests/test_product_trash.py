"""Trash, restore and permanent delete for products.

`DELETE /admin/products/{id}` has always been a soft delete, but the admin list
reused the storefront's query — so a trashed product vanished from the panel
that was supposed to manage it. These cover the recovery path and prove that a
permanent delete leaves order history intact.
"""

import pytest


async def _product(client, admin_headers, name="Trash Me", **extra):
    body = {"name": name, "description": "Leather.", "price": 2500, "stock": 5}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _trash(client, admin_headers, product_id):
    response = await client.delete(
        f"/api/v1/admin/products/{product_id}", headers=admin_headers
    )
    assert response.status_code == 200, response.text


def _slugs(payload) -> set[str]:
    return {item["slug"] for item in payload["items"]}


# ── Listing ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trashed_product_is_findable_in_the_admin_panel(client, admin_headers):
    """The bug: a deleted product disappeared from the admin list entirely."""
    product = await _product(client, admin_headers, name="Gone Missing")
    await _trash(client, admin_headers, product["id"])

    active = await client.get(
        "/api/v1/admin/products?status=active", headers=admin_headers
    )
    assert product["slug"] not in _slugs(active.json())

    trashed = await client.get(
        "/api/v1/admin/products?status=trashed", headers=admin_headers
    )
    assert product["slug"] in _slugs(trashed.json())

    every = await client.get("/api/v1/admin/products?status=all", headers=admin_headers)
    assert product["slug"] in _slugs(every.json())


@pytest.mark.asyncio
async def test_trashed_product_stays_hidden_from_the_storefront(
    client, admin_headers
):
    product = await _product(client, admin_headers, name="Hidden Shop")
    await _trash(client, admin_headers, product["id"])

    listed = await client.get("/api/v1/products")
    assert product["slug"] not in _slugs(listed.json())

    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_admin_search_spans_the_whole_catalog(client, admin_headers):
    """Search runs in the query, not over one page of results."""
    for index in range(8):
        await _product(client, admin_headers, name=f"Filler {index}")
    await _product(client, admin_headers, name="Needle Wallet")

    response = await client.get(
        "/api/v1/admin/products?search=needle&pageSize=5", headers=admin_headers
    )
    assert response.status_code == 200
    assert _slugs(response.json()) == {"needle-wallet"}


@pytest.mark.asyncio
async def test_counts_split_active_and_trashed(client, admin_headers):
    keep = await _product(client, admin_headers, name="Keeper")
    drop = await _product(client, admin_headers, name="Dropper")
    await _trash(client, admin_headers, drop["id"])

    counts = (
        await client.get("/api/v1/admin/products/counts", headers=admin_headers)
    ).json()

    assert counts["active"] >= 1
    assert counts["trashed"] >= 1
    assert counts["all"] == counts["active"] + counts["trashed"]
    assert keep["id"]


# ── Restore ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_puts_the_product_back_on_the_storefront(
    client, admin_headers
):
    product = await _product(client, admin_headers, name="Second Chance")
    await _trash(client, admin_headers, product["id"])

    restored = await client.post(
        f"/api/v1/admin/products/{product['id']}/restore", headers=admin_headers
    )
    assert restored.status_code == 200, restored.text

    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.status_code == 200


# ── Permanent delete ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_purge_a_live_product(client, admin_headers):
    """A single misdirected call must not destroy a product that is on sale."""
    product = await _product(client, admin_headers, name="Still Selling")

    response = await client.delete(
        f"/api/v1/admin/products/{product['id']}/permanent", headers=admin_headers
    )
    assert response.status_code == 409
    assert "trash" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_purge_removes_the_product(client, admin_headers):
    product = await _product(client, admin_headers, name="Really Gone")
    await _trash(client, admin_headers, product["id"])

    response = await client.delete(
        f"/api/v1/admin/products/{product['id']}/permanent", headers=admin_headers
    )
    assert response.status_code == 200, response.text

    trashed = await client.get(
        "/api/v1/admin/products?status=trashed", headers=admin_headers
    )
    assert product["slug"] not in _slugs(trashed.json())


@pytest.mark.asyncio
async def test_purge_leaves_order_history_readable(client, admin_headers, auth_headers):
    """The question that decides whether permanent delete is safe at all.

    An order line keeps its own snapshot of the product and the foreign key is
    ON DELETE SET NULL, so a customer's past order survives the product being
    destroyed — name, price and quantity all still render.
    """
    product = await _product(client, admin_headers, name="Bought Then Deleted")

    placed = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "items": [{"productId": product["id"], "quantity": 2}],
            "shippingAddress": {
                "label": "Home",
                "street": "12 Mall Road",
                "city": "Lahore",
                "state": "Punjab",
                "postalCode": "54000",
                "country": "Pakistan",
            },
            "paymentMethod": "cod",
        },
    )
    assert placed.status_code == 200, placed.text
    order_id = placed.json()["id"]
    order_total = placed.json()["total"]

    await _trash(client, admin_headers, product["id"])
    purged = await client.delete(
        f"/api/v1/admin/products/{product['id']}/permanent", headers=admin_headers
    )
    assert purged.status_code == 200, purged.text

    after = await client.get(f"/api/v1/orders/{order_id}", headers=auth_headers)
    assert after.status_code == 200, after.text

    body = after.json()
    assert body["total"] == order_total
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2
    # The snapshot is what makes this survive — the product row is gone
    assert body["items"][0]["product"]["name"] == "Bought Then Deleted"
