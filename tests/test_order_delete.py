"""Permanently deleting an order — an admin cleanup tool, not a customer
action. There is deliberately no equivalent on the customer or public
routers.

Stock is restored unless the order was already cancelled (which already gave
it back), so deleting a pending test order does not leave inventory
permanently understated. The deletion is logged before the row disappears,
since afterward there is nothing left to look up.
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


async def _order(client, admin_headers, price=1000, stock=10, quantity=2):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Belt", "description": "A belt.", "price": price, "stock": stock},
    )
    pid = product.json()["id"]
    order = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": quantity}]},
    )
    assert order.status_code == 200, order.text
    return pid, order.json()


async def _stock(client, product_id):
    listed = await client.get("/api/v1/products?pageSize=50")
    return next(p for p in listed.json()["items"] if p["id"] == product_id)["stock"]


@pytest.mark.asyncio
async def test_admin_can_delete_an_order(client, admin_headers):
    _, order = await _order(client, admin_headers)

    response = await client.delete(
        f"/api/v1/admin/orders/{order['id']}", headers=admin_headers
    )
    assert response.status_code == 200, response.text

    lookup = await client.get(
        f"/api/v1/admin/orders/{order['id']}", headers=admin_headers
    )
    assert lookup.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_pending_order_restores_stock(client, admin_headers):
    pid, order = await _order(client, admin_headers, stock=10, quantity=3)
    assert await _stock(client, pid) == 7  # reserved at checkout

    await client.delete(f"/api/v1/admin/orders/{order['id']}", headers=admin_headers)
    assert await _stock(client, pid) == 10


@pytest.mark.asyncio
async def test_deleting_an_already_cancelled_order_does_not_double_restore(
    client, admin_headers
):
    pid, order = await _order(client, admin_headers, stock=10, quantity=3)
    await client.post(
        f"/api/v1/admin/orders/{order['id']}/cancel", headers=admin_headers
    )
    assert await _stock(client, pid) == 10  # cancel already gave it back

    await client.delete(f"/api/v1/admin/orders/{order['id']}", headers=admin_headers)
    assert await _stock(client, pid) == 10  # unchanged, not 13


@pytest.mark.asyncio
async def test_deleting_an_unknown_order_is_404(client, admin_headers):
    response = await client.delete(
        "/api/v1/admin/orders/does-not-exist", headers=admin_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_requires_admin(client, auth_headers):
    response = await client.delete(
        "/api/v1/admin/orders/does-not-exist", headers=auth_headers
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_deletion_is_logged_with_the_order_number(client, admin_headers):
    """The row is gone afterward, so the order number has to survive in the
    log's own `details` rather than being looked up after the fact."""
    _, order = await _order(client, admin_headers)
    await client.delete(f"/api/v1/admin/orders/{order['id']}", headers=admin_headers)

    log = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    entry = next(
        i for i in log.json()["items"] if i["action"] == "order_deleted"
    )
    assert entry["entityId"] == order["id"]
    assert entry["detailSummary"] == order["orderNumber"]
