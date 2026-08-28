"""Shipping and tax as store settings, not hardcoded constants.

Both used to be module-level constants in order_service.py
(SHIPPING_COST = 250, FREE_SHIPPING_THRESHOLD = 5000) with no admin control
at all, and duplicated again as magic numbers in the storefront's cart and
checkout components. Tax rate already existed as a saved setting but nothing
ever read it when pricing an order.

Tax applies to (subtotal + shipping) together — the store's own choice, not
a platform default; confirm with the merchant before changing that.
"""

import pytest

ADDRESS = {
    "email": "buyer@example.com",
    "phone": "03001234567",
    "firstName": "Buyer",
    "lastName": "One",
    "street": "1 Test St",
    "city": "Lahore",
    "state": "Punjab",
    "postalCode": "54000",
}


async def _product(client, admin_headers, price=1000, stock=10):
    r = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Belt", "description": "A belt.", "price": price, "stock": stock},
    )
    return r.json()["id"]


async def _set_settings(client, admin_headers, **kwargs):
    response = await client.put(
        "/api/v1/admin/settings", headers=admin_headers, json=kwargs
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── Admin can configure both ─────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_set_shipping_and_tax(client, admin_headers):
    updated = await _set_settings(
        client,
        admin_headers,
        shippingCost=300,
        freeShippingThreshold=6000,
        taxRate=5,
    )
    assert updated["shippingCost"] == 300
    assert updated["freeShippingThreshold"] == 6000
    assert updated["taxRate"] == 5


# ── The public endpoint exposes only pricing, nothing internal ──


@pytest.mark.asyncio
async def test_public_settings_exposes_pricing_only(client, admin_headers):
    await _set_settings(client, admin_headers, storeName="Wrenza Test", taxRate=5)

    response = await client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["taxRate"] == 5
    assert "shippingCost" in body
    assert "freeShippingThreshold" in body
    # `maintenanceMode` is deliberately here — the storefront's root layout
    # reads it on every request to decide whether to show the coming-soon
    # page, which used to be a build-time env var needing a rebuild to flip.
    assert "maintenanceMode" in body
    # Nothing an anonymous visitor has no business seeing.
    assert "storeName" not in body
    assert "contactEmail" not in body


@pytest.mark.asyncio
async def test_public_settings_needs_no_auth(client):
    response = await client.get("/api/v1/settings")
    assert response.status_code == 200, response.text


# ── Checkout actually uses the configured values ─────────────────


@pytest.mark.asyncio
async def test_checkout_uses_configured_shipping_cost(client, admin_headers):
    await _set_settings(client, admin_headers, shippingCost=300, taxRate=0)
    pid = await _product(client, admin_headers, price=1000)

    checkout = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1}]},
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["shipping"] == 300
    assert body["total"] == 1300


@pytest.mark.asyncio
async def test_checkout_waives_shipping_at_the_configured_threshold(
    client, admin_headers
):
    await _set_settings(
        client, admin_headers, shippingCost=300, freeShippingThreshold=2000, taxRate=0
    )
    pid = await _product(client, admin_headers, price=2000)

    checkout = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1}]},
    )
    assert checkout.json()["shipping"] == 0


@pytest.mark.asyncio
async def test_checkout_applies_tax_to_subtotal_plus_shipping(
    client, admin_headers
):
    """1000 subtotal + 250 shipping = 1250 taxable base; 10% tax = 125."""
    await _set_settings(client, admin_headers, shippingCost=250, taxRate=10)
    pid = await _product(client, admin_headers, price=1000)

    checkout = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1}]},
    )
    assert checkout.status_code == 200, checkout.text
    body = checkout.json()
    assert body["tax"] == 125.0
    assert body["total"] == 1375.0


@pytest.mark.asyncio
async def test_authenticated_order_uses_the_same_pricing(
    client, admin_headers, auth_headers
):
    """create_order and create_checkout_order must not drift apart — they
    already did once, which is why _reserve_line_item was unified."""
    await _set_settings(client, admin_headers, shippingCost=250, taxRate=10)
    pid = await _product(client, admin_headers, price=1000)

    response = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "items": [{"productId": pid, "quantity": 1}],
            "shippingAddress": {
                "label": "Home",
                "street": ADDRESS["street"],
                "city": ADDRESS["city"],
                "state": ADDRESS["state"],
                "postalCode": ADDRESS["postalCode"],
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["tax"] == 125.0


@pytest.mark.asyncio
async def test_tax_defaults_to_zero_when_unset(client, admin_headers):
    """A store that never touches the tax field must not silently start
    charging one."""
    pid = await _product(client, admin_headers, price=1000)

    checkout = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1}]},
    )
    assert checkout.json()["tax"] == 0


# ── Maintenance mode ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_maintenance_mode_defaults_to_off(client):
    response = await client.get("/api/v1/settings")
    assert response.json()["maintenanceMode"] is False


@pytest.mark.asyncio
async def test_maintenance_mode_reflects_the_admin_toggle(client, admin_headers):
    await _set_settings(client, admin_headers, maintenanceMode=True)

    response = await client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    assert response.json()["maintenanceMode"] is True

    await _set_settings(client, admin_headers, maintenanceMode=False)
    response = await client.get("/api/v1/settings")
    assert response.json()["maintenanceMode"] is False
