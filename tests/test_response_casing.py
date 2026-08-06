"""Every response body the storefront consumes must be camelCase.

Routers that return service dicts bypass Pydantic's alias generator, so a
snake_case key can leak in unnoticed — it has happened twice (`image_url` on
the category tree, `postal_code` on addresses). These tests walk real payloads
and fail on any snake_case key, so the next one is caught here rather than by
a `undefined` in the storefront.
"""

import pytest

SNAKE = "_"


def _snake_keys(payload, path="") -> list[str]:
    """Every snake_case key in a nested payload, with its path."""
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            where = f"{path}.{key}" if path else key
            # Leading underscores are not the casing bug we are hunting
            if SNAKE in key.strip(SNAKE):
                found.append(where)
            found.extend(_snake_keys(value, where))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            found.extend(_snake_keys(item, f"{path}[{index}]"))
    return found


async def _seed_product(client, admin_headers, **extra):
    body = {"name": "Casing Wallet", "description": "Leather.", "price": 3000}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_public_endpoints_are_camel_case(client, admin_headers):
    product = await _seed_product(client, admin_headers)
    await client.put(
        f"/api/v1/admin/products/{product['id']}/faqs",
        headers=admin_headers,
        json={"faqs": [{"question": "Is it leather?", "answer": "Yes."}]},
    )

    paths = [
        "/api/v1/products",
        "/api/v1/products/filters",
        f"/api/v1/products/{product['slug']}",
        f"/api/v1/products/{product['slug']}/reviews",
        "/api/v1/categories",
        "/api/v1/collections",
        "/api/v1/banners",
        "/api/v1/testimonials",
    ]

    offenders = {}
    for path in paths:
        response = await client.get(path)
        assert response.status_code == 200, f"{path} -> {response.text}"
        keys = _snake_keys(response.json())
        if keys:
            offenders[path] = keys

    assert not offenders, f"snake_case keys in public responses: {offenders}"


@pytest.mark.asyncio
async def test_customer_endpoints_are_camel_case(client, auth_headers):
    created = await client.post(
        "/api/v1/addresses",
        headers=auth_headers,
        json={
            "label": "Home",
            "street": "12 Mall Road",
            "city": "Lahore",
            "state": "Punjab",
            "postalCode": "54000",
            "country": "Pakistan",
            "isDefault": True,
        },
    )
    assert created.status_code == 200, created.text
    assert not _snake_keys(created.json()), created.json()

    listed = await client.get("/api/v1/addresses", headers=auth_headers)
    assert listed.status_code == 200
    assert not _snake_keys(listed.json()), listed.json()

    # The field that actually leaked before
    assert "postalCode" in listed.json()[0]
    assert "postal_code" not in listed.json()[0]

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    assert not _snake_keys(me.json()), me.json()


@pytest.mark.asyncio
async def test_review_creation_is_camel_case(client, admin_headers, auth_headers):
    product = await _seed_product(client, admin_headers, name="Reviewed Casing")

    response = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={"productId": product["id"], "rating": 5, "comment": "Great."},
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert not _snake_keys(body), body
    assert "userName" in body
    assert "user_name" not in body


@pytest.mark.asyncio
async def test_order_payloads_are_camel_case(client, admin_headers, auth_headers):
    """Order items embed a product snapshot dict, which bypasses Pydantic
    aliasing — the account pages read it directly."""
    product = await _seed_product(
        client, admin_headers, name="Ordered Casing", stock=5
    )

    placed = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "items": [{"productId": product["id"], "quantity": 1}],
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
    assert not _snake_keys(placed.json()), _snake_keys(placed.json())

    listed = await client.get("/api/v1/orders", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert not _snake_keys(listed.json()), _snake_keys(listed.json())
