"""The order detail page's status timeline.

Nothing recorded when an order moved between statuses before this — `status`
was simply overwritten on each transition, and the timeline would otherwise
have nothing to draw. Every transition is now logged to `activity_logs`
(entity="order"), which already existed with a working read endpoint but
nothing had ever written to it.
"""

import pytest
import pytest_asyncio

ADDRESS = {
    "email": "buyer@example.com",
    "phone": "03001234567",
    "firstName": "Ayesha",
    "lastName": "Khan",
    "street": "1 Test St",
    "city": "Lahore",
    "state": "Punjab",
    "postalCode": "54000",
}


@pytest_asyncio.fixture
async def placed_order(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Belt", "description": "A belt.", "price": 1000, "stock": 10},
    )
    pid = product.json()["id"]
    order = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1}]},
    )
    assert order.status_code == 200, order.text
    return order.json()


@pytest.mark.asyncio
async def test_a_status_change_appears_in_the_timeline(
    client, admin_headers, placed_order
):
    order_id = placed_order["id"]
    response = await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "confirmed"},
    )
    assert response.status_code == 200, response.text

    detail = await client.get(
        f"/api/v1/admin/orders/{order_id}", headers=admin_headers
    )
    history = detail.json()["statusHistory"]
    assert len(history) == 1
    assert history[0]["fromStatus"] == "pending"
    assert history[0]["toStatus"] == "confirmed"
    assert history[0]["changedBy"] == "Admin User"


@pytest.mark.asyncio
async def test_multiple_transitions_appear_oldest_first(
    client, admin_headers, placed_order
):
    order_id = placed_order["id"]
    await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "confirmed"},
    )
    await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "processing"},
    )

    detail = await client.get(
        f"/api/v1/admin/orders/{order_id}", headers=admin_headers
    )
    history = detail.json()["statusHistory"]
    assert [h["toStatus"] for h in history] == ["confirmed", "processing"]


@pytest.mark.asyncio
async def test_cancelling_logs_a_transition_too(
    client, admin_headers, placed_order
):
    """Cancel is a separate code path from the status endpoint — it needs the
    same logging, not just the PUT /status route."""
    order_id = placed_order["id"]
    response = await client.post(
        f"/api/v1/admin/orders/{order_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 200, response.text

    detail = await client.get(
        f"/api/v1/admin/orders/{order_id}", headers=admin_headers
    )
    history = detail.json()["statusHistory"]
    assert history[-1]["toStatus"] == "cancelled"


@pytest.mark.asyncio
async def test_a_fresh_order_has_no_history_yet(client, admin_headers, placed_order):
    detail = await client.get(
        f"/api/v1/admin/orders/{placed_order['id']}", headers=admin_headers
    )
    assert detail.json()["statusHistory"] == []


@pytest.mark.asyncio
async def test_history_is_not_returned_in_the_admin_listing(
    client, admin_headers, placed_order
):
    """A history query per row would be paid on every page load of a listing
    that never displays it."""
    await client.put(
        f"/api/v1/admin/orders/{placed_order['id']}/status",
        headers=admin_headers,
        json={"status": "confirmed"},
    )

    listing = await client.get("/api/v1/admin/orders", headers=admin_headers)
    assert listing.status_code == 200, listing.text
    row = next(o for o in listing.json()["items"] if o["id"] == placed_order["id"])
    assert row.get("statusHistory", []) == []
