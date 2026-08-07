"""Email dispatch and password reset.

Nothing here touches SMTP: `send_email` is replaced with a capture list, and
`enqueue` runs its job inline so a test can assert on the message a real
checkout would produce.
"""

import pytest

from app.core.config import get_settings
from app.services.email import sender as email_sender
from app.tasks import email_tasks


@pytest.fixture(autouse=True)
def shop_address(monkeypatch):
    """Pin ADMIN_EMAIL so these tests do not read the developer's .env.

    Both shop-facing emails are skipped when it is unset, and it defaults to
    "". That made the suite pass on a machine whose .env happened to define it
    and fail anywhere else — CI found this, not a local run.
    """
    monkeypatch.setattr(get_settings(), "ADMIN_EMAIL", "shop@wrenza.test")


@pytest.fixture
def outbox(monkeypatch):
    """Captured messages instead of sent ones."""
    sent: list[dict] = []

    async def fake_send(mailbox, to, subject, html, text, reply_to=None):
        sent.append(
            {
                "mailbox": mailbox.value,
                "to": to,
                "subject": subject,
                "html": html,
                "text": text,
                "reply_to": reply_to,
            }
        )
        return True

    # Patched where it is used, not where it is defined — the tasks module
    # imported the name at import time.
    monkeypatch.setattr(email_tasks, "send_email", fake_send)
    monkeypatch.setattr(email_sender, "send_email", fake_send)
    return sent


@pytest.fixture
def run_jobs(monkeypatch):
    """Run enqueued jobs immediately, in-process.

    The real queue hands work to a separate worker; a test wants the effect
    without the process.
    """
    from app.services import auth_service, order_service
    from app.api.public import contact as contact_router

    from tests.conftest import TestingSessionLocal

    # The tasks open their own session via `AsyncSessionLocal`, which points at
    # the real database — `conftest` only overrides the `get_db` dependency.
    # Without this the job would query Postgres for a row that exists only in
    # the test database.
    monkeypatch.setattr(email_tasks, "AsyncSessionLocal", TestingSessionLocal)

    async def immediate(job: str, *args, **kwargs):
        fn = getattr(email_tasks, job, None)
        if fn is None:
            return False
        await fn({}, *args, **kwargs)
        return True

    for module in (order_service, auth_service, contact_router):
        monkeypatch.setattr(module, "enqueue", immediate)
    return immediate


async def _product(client, admin_headers, **extra):
    body = {"name": "Email Wallet", "description": "Leather.", "price": 3000, "stock": 5}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _checkout(client, product_id, email="buyer@example.com"):
    return await client.post(
        "/api/v1/checkout",
        json={
            "items": [{"productId": product_id, "quantity": 2}],
            "email": email,
            "phone": "03001234567",
            "firstName": "Ayesha",
            "lastName": "Khan",
            "street": "12 Mall Road",
            "city": "Lahore",
            "state": "Punjab",
            "postalCode": "54000",
        },
    )


# ── Order emails ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_checkout_emails_customer_and_shop(
    client, admin_headers, outbox, run_jobs
):
    product = await _product(client, admin_headers)
    placed = await _checkout(client, product["id"])
    assert placed.status_code == 200, placed.text

    assert len(outbox) == 2, "expected a customer confirmation and a shop alert"

    customer, alert = outbox[0], outbox[1]
    assert customer["to"] == "buyer@example.com"
    assert customer["mailbox"] == "order"
    assert placed.json()["orderNumber"] in customer["subject"]
    # The item and what it cost must both survive into the message
    assert "Email Wallet" in customer["html"]
    assert "6,000" in customer["html"]

    assert alert["subject"].startswith("New order")
    assert "Ayesha Khan" in alert["html"]


@pytest.mark.asyncio
async def test_smtp_failure_returns_false_rather_than_raising(monkeypatch):
    """The customer has paid. An SMTP outage is not their problem.

    `send_email` swallows the error and reports it, so a caller — and the
    worker running it — carries on.
    """
    import aiosmtplib

    async def explode(*args, **kwargs):
        raise aiosmtplib.SMTPConnectError("connection refused")

    monkeypatch.setattr(aiosmtplib, "send", explode)

    sent = await email_sender.send_email(
        email_sender.Mailbox.ORDER,
        to="buyer@example.com",
        subject="Order confirmed",
        html="<p>hi</p>",
        text="hi",
    )
    assert sent is False


@pytest.mark.asyncio
async def test_a_dead_queue_does_not_fail_the_order(client, admin_headers, monkeypatch):
    """Redis being down must not cost a sale.

    No `run_jobs` here: the real `enqueue` runs, and in the test environment
    there is no queue connection — exactly the failure being guarded against.
    """
    product = await _product(client, admin_headers, name="Resilient Wallet")
    placed = await _checkout(client, product["id"])

    assert placed.status_code == 200, placed.text
    assert placed.json()["orderNumber"]


@pytest.mark.asyncio
async def test_status_email_only_on_shipped_and_delivered(
    client, admin_headers, outbox, run_jobs
):
    product = await _product(client, admin_headers, name="Status Wallet")
    order_id = (await _checkout(client, product["id"])).json()["id"]
    outbox.clear()

    # Orders move pending → confirmed → processing → shipped. The steps
    # before shipping are internal and must stay quiet.
    for status in ("confirmed", "processing"):
        response = await client.put(
            f"/api/v1/admin/orders/{order_id}/status",
            headers=admin_headers,
            json={"status": status},
        )
        assert response.status_code == 200, response.text
    assert outbox == [], "internal transitions should not email the customer"

    response = await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "shipped", "trackingNumber": "TCS-9911"},
    )
    assert response.status_code == 200, response.text

    assert len(outbox) == 1
    assert "On its way" in outbox[0]["subject"]
    assert "TCS-9911" in outbox[0]["html"]

    response = await client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        headers=admin_headers,
        json={"status": "delivered"},
    )
    assert response.status_code == 200, response.text
    assert len(outbox) == 2
    assert "Delivered" in outbox[1]["subject"]


@pytest.mark.asyncio
async def test_cancelling_emails_the_customer(
    client, admin_headers, outbox, run_jobs
):
    product = await _product(client, admin_headers, name="Cancelled Wallet")
    order_id = (await _checkout(client, product["id"])).json()["id"]
    outbox.clear()

    response = await client.post(
        f"/api/v1/admin/orders/{order_id}/cancel", headers=admin_headers
    )
    assert response.status_code == 200, response.text

    assert len(outbox) == 1
    assert "cancelled" in outbox[0]["subject"].lower()


# ── Contact form ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contact_form_emails_the_shop(client, outbox, run_jobs):
    response = await client.post(
        "/api/v1/contact",
        json={
            "name": "Ayesha Khan",
            "email": "ayesha@example.com",
            "subject": "Belt sizing",
            "message": "Which size for a 34in waist?",
        },
    )
    assert response.status_code == 200, response.text

    assert len(outbox) == 1
    enquiry = outbox[0]
    assert enquiry["mailbox"] == "info"
    # Replying must reach the person who asked, not info@
    assert enquiry["reply_to"] == "ayesha@example.com"
    assert "34in waist" in enquiry["html"]


# ── Password reset ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_flow_end_to_end(client, test_user, outbox, run_jobs):
    """The endpoint used to claim success and do nothing at all."""
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": test_user.email}
    )
    assert response.status_code == 200

    assert len(outbox) == 1
    assert outbox[0]["mailbox"] == "info"

    # Pull the token out of the link, the way a customer clicking it would
    token = outbox[0]["html"].split("token=")[1].split('"')[0].split("<")[0]

    reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "newPassword": "brand-new-password"},
    )
    assert reset.status_code == 200, reset.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "brand-new-password"},
    )
    assert login.status_code == 200, "new password should work"


@pytest.mark.asyncio
async def test_reset_link_works_only_once(client, test_user, outbox, run_jobs):
    """The link lives in an inbox forever; a second click must not work."""
    await client.post("/api/v1/auth/forgot-password", json={"email": test_user.email})
    token = outbox[0]["html"].split("token=")[1].split('"')[0].split("<")[0]

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "newPassword": "first-new-password"},
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "newPassword": "second-new-password"},
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_an_access_token_cannot_reset_a_password(client, test_user, auth_headers):
    """Purpose is checked, so a session token is not a reset token."""
    access = auth_headers["Authorization"].removeprefix("Bearer ")

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": access, "newPassword": "should-not-work"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_forgot_password_says_the_same_for_unknown_emails(client, outbox, run_jobs):
    """A different reply would let anyone test which addresses are registered."""
    known = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert known.status_code == 200
    assert "if an account" in known.json()["message"].lower()
    assert outbox == [], "no email for an address with no account"


@pytest.mark.asyncio
async def test_a_reset_token_cannot_be_used_as_a_session(client, test_user):
    """A reset link must not double as an API session.

    With `type: "access"` on the reset token it did: the auth dependency only
    screens on that field, so anyone seeing the URL — a forwarded email, shared
    browser, referer header — could act as the account holder for 30 minutes.
    """
    from app.core.security import create_password_reset_token

    token = create_password_reset_token(test_user.id)

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401, "a reset token must not authenticate"


@pytest.mark.asyncio
async def test_reset_tokens_cannot_be_refreshed_into_a_session(client, test_user):
    """The refresh path is the other way the same confusion could be reached."""
    from app.core.security import create_password_reset_token

    token = create_password_reset_token(test_user.id)

    response = await client.post("/api/v1/auth/refresh", json={"refreshToken": token})
    assert response.status_code == 401
