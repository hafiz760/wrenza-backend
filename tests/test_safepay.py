"""Safepay online-payment checkout.

The gateway calls themselves (create_tracker, create_passport_token) are
monkeypatched out — they're network calls to a third party, not something
this suite should depend on being reachable. What's actually under test:
the admin kill switch, order state transitions, and webhook signature
verification (a pure function, genuinely tested end to end with a real
HMAC).
"""

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from app.services import order_service, safepay_service

WEBHOOK_SECRET = "test-webhook-secret"


async def _product(client, admin_headers, price=1000, stock=10):
    r = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Belt", "description": "A belt.", "price": price, "stock": stock},
    )
    return r.json()["id"]


def _checkout_payload(product_id):
    return {
        "items": [{"productId": product_id, "quantity": 1}],
        "email": "buyer@example.com",
        "phone": "03001234567",
        "firstName": "Buyer",
        "lastName": "One",
        "street": "1 Test St",
        "city": "Lahore",
        "state": "Punjab",
        "postalCode": "54000",
    }


def _sign(payload_bytes: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha512).hexdigest()


@pytest.fixture
def fake_safepay(monkeypatch):
    """Skips the real HTTP calls; returns deterministic tracker/tbt values."""

    async def fake_create_tracker(amount, order_id, order_number):
        return "track_test-123"

    async def fake_create_passport_token():
        return "tbt-test-token"

    monkeypatch.setattr(safepay_service, "create_tracker", fake_create_tracker)
    monkeypatch.setattr(safepay_service, "create_passport_token", fake_create_passport_token)


@pytest.fixture
def webhook_secret_settings(monkeypatch):
    """Points safepay_service at a known webhook secret without touching the
    process-wide lru_cache'd Settings singleton other tests rely on."""
    fake_settings = SimpleNamespace(
        SAFEPAY_WEBHOOK_SECRET=WEBHOOK_SECRET,
        SAFEPAY_ENVIRONMENT="sandbox",
        SAFEPAY_PUBLIC_KEY="pub",
        SAFEPAY_SECRET_KEY="sec",
    )
    monkeypatch.setattr(safepay_service, "get_settings", lambda: fake_settings)


async def _enable_safepay(client, admin_headers):
    response = await client.put(
        "/api/v1/admin/settings", headers=admin_headers, json={"safepayEnabled": True}
    )
    assert response.status_code == 200, response.text


# ── Admin kill switch ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_safepay_checkout_disabled_by_default(client, admin_headers):
    pid = await _product(client, admin_headers)
    response = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_safepay_checkout_works_once_enabled(client, admin_headers, fake_safepay):
    await _enable_safepay(client, admin_headers)
    pid = await _product(client, admin_headers, stock=5)

    response = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checkoutUrl"].startswith("https://sandbox.api.getsafepay.com/embedded?")
    assert "track_test-123" in body["checkoutUrl"]
    assert body["orderNumber"]


@pytest.mark.asyncio
async def test_safepay_checkout_reserves_stock_like_cod(client, admin_headers, fake_safepay):
    """Same stock semantics as Cash on Delivery — reserved at order
    creation, not at payment confirmation. See order_service._build_order."""
    await _enable_safepay(client, admin_headers)
    pid = await _product(client, admin_headers, stock=1)

    response = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    assert response.status_code == 200, response.text

    # Stock is now 0 — a second purchase attempt must fail.
    second = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    assert second.status_code == 400


# ── Order left unpaid until the webhook confirms it ──────────────


@pytest.mark.asyncio
async def test_safepay_order_starts_unpaid(client, admin_headers, fake_safepay):
    await _enable_safepay(client, admin_headers)
    pid = await _product(client, admin_headers)

    response = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    order_id = response.json()["orderId"]

    order = await client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert order.json()["paymentStatus"] == "unpaid"
    assert order.json()["paymentMethod"] == "Safepay"


# ── Webhook signature verification (real HMAC, no mocking) ───────


def test_webhook_signature_accepts_correctly_signed_payload(webhook_secret_settings):
    payload = json.dumps({"type": "payment.succeeded", "data": {"tracker": "track_1"}}).encode()
    signature = _sign(payload)
    event = safepay_service.verify_webhook_signature(payload, signature)
    assert event["type"] == "payment.succeeded"


def test_webhook_signature_rejects_wrong_secret(webhook_secret_settings):
    payload = json.dumps({"type": "payment.succeeded", "data": {"tracker": "track_1"}}).encode()
    bad_signature = _sign(payload, secret="not-the-real-secret")
    with pytest.raises(safepay_service.SafepayError):
        safepay_service.verify_webhook_signature(payload, bad_signature)


def test_webhook_signature_rejects_tampered_payload(webhook_secret_settings):
    payload = json.dumps({"type": "payment.succeeded", "data": {"tracker": "track_1"}}).encode()
    signature = _sign(payload)
    tampered = json.dumps({"type": "payment.succeeded", "data": {"tracker": "track_2"}}).encode()
    with pytest.raises(safepay_service.SafepayError):
        safepay_service.verify_webhook_signature(tampered, signature)


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature_header(client):
    response = await client.post(
        "/api/v1/webhooks/safepay", json={"type": "payment.succeeded", "data": {}}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(client):
    response = await client.post(
        "/api/v1/webhooks/safepay",
        json={"type": "payment.succeeded", "data": {"tracker": "track_x"}},
        headers={"X-SFPY-SIGNATURE": "not-a-real-signature"},
    )
    assert response.status_code == 400


# ── End-to-end: initiate → webhook marks it paid ──────────────────


@pytest.mark.asyncio
async def test_webhook_marks_order_paid_and_is_idempotent(
    client, admin_headers, fake_safepay, webhook_secret_settings
):
    await _enable_safepay(client, admin_headers)
    pid = await _product(client, admin_headers)

    initiate = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    order_id = initiate.json()["orderId"]

    payload = json.dumps(
        {"type": "payment.succeeded", "data": {"tracker": "track_test-123", "amount": 1000}}
    ).encode()
    signature = _sign(payload)

    first = await client.post(
        "/api/v1/webhooks/safepay",
        content=payload,
        headers={"X-SFPY-SIGNATURE": signature, "Content-Type": "application/json"},
    )
    assert first.status_code == 200

    order = await client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert order.json()["paymentStatus"] == "paid"

    # A retried webhook (Safepay resends until it sees a 200) must not
    # error or double-apply anything.
    second = await client.post(
        "/api/v1/webhooks/safepay",
        content=payload,
        headers={"X-SFPY-SIGNATURE": signature, "Content-Type": "application/json"},
    )
    assert second.status_code == 200

    order_again = await client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert order_again.json()["paymentStatus"] == "paid"


@pytest.mark.asyncio
async def test_webhook_marks_order_failed(
    client, admin_headers, fake_safepay, webhook_secret_settings
):
    await _enable_safepay(client, admin_headers)
    pid = await _product(client, admin_headers)

    initiate = await client.post("/api/v1/checkout/safepay", json=_checkout_payload(pid))
    order_id = initiate.json()["orderId"]

    payload = json.dumps(
        {"type": "payment.failed", "data": {"tracker": "track_test-123"}}
    ).encode()
    signature = _sign(payload)

    response = await client.post(
        "/api/v1/webhooks/safepay",
        content=payload,
        headers={"X-SFPY-SIGNATURE": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200

    order = await client.get(f"/api/v1/admin/orders/{order_id}", headers=admin_headers)
    assert order.json()["paymentStatus"] == "failed"
