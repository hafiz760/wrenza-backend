"""The activity log, in a form an admin can actually read.

Previously every row showed a raw snake_case `action` and a bare UUID for
`entityId` — accurate, but meant nothing to a human glancing at the page.
Nothing here changes what gets logged, only what the read endpoint adds on
top: a resolved actor name, a plain action sentence, an order number instead
of an id, and a one-line summary of `details`.
"""

import pytest


async def _order_and_status_change(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Belt", "description": "A belt.", "price": 1000, "stock": 5},
    )
    pid = product.json()["id"]
    order = await client.post(
        "/api/v1/checkout",
        json={
            "email": "buyer@example.com",
            "phone": "03001234567",
            "firstName": "Buyer",
            "lastName": "One",
            "street": "1 Test St",
            "city": "Lahore",
            "state": "Punjab",
            "postalCode": "54000",
            "items": [{"productId": pid, "quantity": 1}],
        },
    )
    order_id = order.json()["id"]
    await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "confirmed"},
    )
    return order_id, order.json()["orderNumber"]


@pytest.mark.asyncio
async def test_log_resolves_the_admin_name(client, admin_headers):
    await _order_and_status_change(client, admin_headers)

    response = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    assert response.status_code == 200, response.text
    entry = response.json()["items"][0]
    assert entry["userName"] == "Admin User"


@pytest.mark.asyncio
async def test_log_resolves_the_order_number_not_a_bare_id(client, admin_headers):
    order_id, order_number = await _order_and_status_change(client, admin_headers)

    response = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    entry = response.json()["items"][0]
    assert entry["entityId"] == order_id
    assert entry["entityLabel"] == order_number


@pytest.mark.asyncio
async def test_log_has_a_readable_action_label(client, admin_headers):
    await _order_and_status_change(client, admin_headers)

    response = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    entry = response.json()["items"][0]
    assert entry["action"] == "order_status_changed"
    assert entry["actionLabel"] == "Order status changed"


@pytest.mark.asyncio
async def test_log_summarises_the_from_to_transition(client, admin_headers):
    await _order_and_status_change(client, admin_headers)

    response = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    entry = response.json()["items"][0]
    assert entry["detailSummary"] == "pending → confirmed"


@pytest.mark.asyncio
async def test_unknown_action_falls_back_to_its_raw_value(client, admin_headers):
    """An action added later, before this endpoint knows a phrase for it,
    must still render — not error, not disappear."""
    from app.db.models.activity_log import ActivityLog
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        db.add(
            ActivityLog(
                action="something_new",
                entity="widget",
                entity_id="not-a-real-uuid",
            )
        )
        await db.commit()

    response = await client.get("/api/v1/admin/activity-log", headers=admin_headers)
    assert response.status_code == 200, response.text
    entry = next(i for i in response.json()["items"] if i["action"] == "something_new")
    assert entry["actionLabel"] == "something_new"
    assert entry["entityLabel"] is None
