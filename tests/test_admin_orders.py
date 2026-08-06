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
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 3}]},
    )
    assert order.status_code == 200, order.text
    return {"product_id": pid, "order": order.json()}


async def _stock(client, product_id):
    listed = await client.get("/api/v1/products?pageSize=50")
    return next(p for p in listed.json()["items"] if p["id"] == product_id)["stock"]


@pytest.mark.asyncio
async def test_admin_can_get_single_order(client, admin_headers, placed_order):
    order_id = placed_order["order"]["id"]
    response = await client.get(
        f"/api/v1/admin/orders/{order_id}", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["orderNumber"] == placed_order["order"]["orderNumber"]


@pytest.mark.asyncio
async def test_admin_order_missing_returns_404(client, admin_headers):
    response = await client.get(
        "/api/v1/admin/orders/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_order_exposes_customer_details(client, admin_headers, placed_order):
    listed = await client.get("/api/v1/admin/orders", headers=admin_headers)
    row = listed.json()["items"][0]
    assert row["customerName"] == "Ayesha Khan"
    assert row["email"] == "buyer@example.com"
    assert row["phone"] == "03001234567"


@pytest.mark.asyncio
async def test_cancel_restores_stock(client, admin_headers, placed_order):
    pid = placed_order["product_id"]
    assert await _stock(client, pid) == 7  # 10 - 3

    response = await client.post(
        f"/api/v1/admin/orders/{placed_order['order']['id']}/cancel",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert await _stock(client, pid) == 10  # restored


@pytest.mark.asyncio
async def test_status_update_to_cancelled_also_restores_stock(
    client, admin_headers, placed_order
):
    pid = placed_order["product_id"]
    response = await client.put(
        f"/api/v1/admin/orders/{placed_order['order']['id']}/status",
        headers=admin_headers,
        json={"status": "cancelled"},
    )
    assert response.status_code == 200
    assert await _stock(client, pid) == 10


@pytest.mark.asyncio
async def test_cannot_cancel_twice(client, admin_headers, placed_order):
    order_id = placed_order["order"]["id"]
    await client.post(f"/api/v1/admin/orders/{order_id}/cancel", headers=admin_headers)

    second = await client.post(
        f"/api/v1/admin/orders/{order_id}/cancel", headers=admin_headers
    )
    assert second.status_code == 400
    assert "already cancelled" in second.json()["detail"]

    # Stock must not be credited twice
    assert await _stock(client, placed_order["product_id"]) == 10


@pytest.mark.asyncio
async def test_search_by_order_number(client, admin_headers, placed_order):
    number = placed_order["order"]["orderNumber"]
    response = await client.get(
        f"/api/v1/admin/orders?search={number}", headers=admin_headers
    )
    assert [o["orderNumber"] for o in response.json()["items"]] == [number]


@pytest.mark.asyncio
async def test_search_by_customer_name_and_email(client, admin_headers, placed_order):
    by_name = await client.get(
        "/api/v1/admin/orders?search=Ayesha", headers=admin_headers
    )
    assert by_name.json()["total"] == 1

    by_email = await client.get(
        "/api/v1/admin/orders?search=buyer@example.com", headers=admin_headers
    )
    assert by_email.json()["total"] == 1

    no_match = await client.get(
        "/api/v1/admin/orders?search=nobody", headers=admin_headers
    )
    assert no_match.json()["total"] == 0


@pytest.mark.asyncio
async def test_date_range_filter(client, admin_headers, placed_order):
    future = await client.get(
        "/api/v1/admin/orders?dateFrom=2099-01-01T00:00:00", headers=admin_headers
    )
    assert future.json()["total"] == 0

    past = await client.get(
        "/api/v1/admin/orders?dateFrom=2000-01-01T00:00:00", headers=admin_headers
    )
    assert past.json()["total"] == 1


@pytest.mark.asyncio
async def test_cancel_restores_variation_stock(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Var Wallet", "description": "x", "kind": "variable", "price": 100},
    )
    pid = product.json()["id"]
    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Colour"}
    )
    aid = attr.json()["id"]
    term = await client.post(
        f"/api/v1/admin/attributes/{aid}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    await client.put(
        f"/api/v1/admin/products/{pid}/attributes",
        headers=admin_headers,
        json={"attributes": [{"attributeId": aid, "termIds": [term.json()["id"]]}]},
    )
    generated = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    vid = generated.json()[0]["id"]
    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={"variations": [{"id": vid, "stock": 5}]},
    )

    order = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 2, "variationId": vid}]},
    )
    await client.post(
        f"/api/v1/admin/orders/{order.json()['id']}/cancel", headers=admin_headers
    )

    listed = await client.get(
        f"/api/v1/admin/products/{pid}/variations", headers=admin_headers
    )
    assert next(v for v in listed.json() if v["id"] == vid)["stock"] == 5


@pytest.mark.asyncio
async def test_customer_can_cancel_own_order_only(client, admin_headers, placed_order, auth_headers):
    order_id = placed_order["order"]["id"]
    # Guest order has no user_id, so a logged-in customer must not reach it
    response = await client.post(
        f"/api/v1/orders/{order_id}/cancel", headers=auth_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_order_routes_require_admin(client, auth_headers, placed_order):
    order_id = placed_order["order"]["id"]
    assert (
        await client.get(f"/api/v1/admin/orders/{order_id}", headers=auth_headers)
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/admin/orders/{order_id}/cancel", headers=auth_headers
        )
    ).status_code == 403
