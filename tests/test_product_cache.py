"""Product caching, and the invalidation that keeps it honest.

The cache layer existed for a long time without being wired up: the TTL tiers,
the namespace and every `cache_delete_pattern` call were in place, but nothing
called `cache_set`, so the invalidation was clearing keys that were never
written. These tests cover the read paths now that they cache, and — more
importantly — the write paths that have to clear them.

Stock is the reason this matters. It is part of the cached product detail and
detail is held for two hours, so a purchase that fails to invalidate leaves a
sold-out product advertising itself as in stock.
"""

import pytest

from tests.conftest import mock_redis


async def _product(client, admin_headers, name="Cached Wallet", **extra):
    body = {"name": name, "description": "Leather.", "price": 4500, "stock": 10}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


def _keys(prefix="wz:products:"):
    return [k for k in mock_redis.store if k.startswith(prefix)]


# ── Reads populate the cache ────────────────────────────────────


@pytest.mark.asyncio
async def test_detail_is_cached(client, admin_headers):
    product = await _product(client, admin_headers)

    await client.get(f"/api/v1/products/{product['slug']}")
    assert f"wz:products:detail:{product['slug']}" in mock_redis.store


@pytest.mark.asyncio
async def test_cached_detail_is_served_and_matches(client, admin_headers):
    """A cache hit must round-trip to the same payload, not a degraded one."""
    product = await _product(client, admin_headers)

    first = await client.get(f"/api/v1/products/{product['slug']}")
    second = await client.get(f"/api/v1/products/{product['slug']}")

    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.asyncio
async def test_listing_is_cached_per_filter(client, admin_headers):
    """Two different filters must not share one entry."""
    await _product(client, admin_headers)

    await client.get("/api/v1/products?page=1")
    await client.get("/api/v1/products?page=2")

    assert len(_keys("wz:products:list:")) == 2


# ── Writes clear it ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_editing_a_product_clears_the_cache(client, admin_headers):
    product = await _product(client, admin_headers)
    await client.get(f"/api/v1/products/{product['slug']}")
    assert _keys()

    response = await client.put(
        f"/api/v1/admin/products/{product['id']}",
        headers=admin_headers,
        json={"name": "Renamed Wallet"},
    )
    assert response.status_code == 200, response.text
    assert _keys() == [], "stale product cache survived an edit"


@pytest.mark.asyncio
async def test_checkout_clears_the_cache_so_stock_is_current(
    client, admin_headers
):
    """The overselling case: buy the last units, then read stock again."""
    product = await _product(client, admin_headers, name="Last Units", stock=10)

    await client.get(f"/api/v1/products/{product['slug']}")

    checkout = await client.post(
        "/api/v1/checkout",
        json={
            "email": "buyer@example.com",
            "phone": "03001234567",
            "firstName": "Buyer",
            "lastName": "One",
            "street": "1 Test Street",
            "city": "Lahore",
            "state": "Punjab",
            "postalCode": "54000",
            "items": [{"productId": product["id"], "quantity": 3}],
        },
    )
    assert checkout.status_code == 200, checkout.text

    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.json()["stock"] == 7, "cache served pre-purchase stock"


@pytest.mark.asyncio
async def test_review_approval_clears_featured(client, admin_headers):
    """Approving a review moves the rating, which the list payload carries."""
    product = await _product(client, admin_headers, isFeatured=True)
    await client.get("/api/v1/products/featured")
    assert _keys("wz:products:featured")

    created = await client.post(
        "/api/v1/reviews",
        json={
            "productId": product["id"],
            "rating": 5,
            "comment": "Excellent.",
            "name": "Guest",
            "email": "g@example.com",
        },
    )
    assert created.status_code == 200, created.text

    await client.put(
        f"/api/v1/admin/reviews/{created.json()['id']}/approve?approved=true",
        headers=admin_headers,
    )
    assert _keys("wz:products:featured") == []
