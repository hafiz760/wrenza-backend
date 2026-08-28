"""Safepay hosted-checkout integration.

Flow: create a "tracker" (Safepay's term for a payment session) → attach our
order id as metadata for reconciliation on their dashboard → mint a
short-lived auth token ("passport") → build the hosted checkout URL the
customer gets redirected to. Safepay confirms the outcome asynchronously via
webhook, not on the redirect back — the redirect is just where the customer's
browser ends up, never trust it for payment state.

Sandbox and production use *different* hosts for the checkout page (not just
different API hosts) — confirmed against Safepay's own PHP SDK
(`Checkout::constructURL`), since their public docs don't spell this out:
sandbox checkout lives on the same host as the sandbox API, production
checkout lives on the bare apex domain, not `api.`.
"""

import hashlib
import hmac
import json

import httpx

from app.core.config import get_settings

_API_HOSTS = {
    "sandbox": "https://sandbox.api.getsafepay.com",
    "production": "https://api.getsafepay.com",
}
_CHECKOUT_HOSTS = {
    "sandbox": "https://sandbox.api.getsafepay.com",
    "production": "https://getsafepay.com",
}


def _api_base() -> str:
    return _API_HOSTS[get_settings().SAFEPAY_ENVIRONMENT]


def _checkout_base() -> str:
    return _CHECKOUT_HOSTS[get_settings().SAFEPAY_ENVIRONMENT]


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "X-SFPY-MERCHANT-SECRET": get_settings().SAFEPAY_SECRET_KEY,
    }


class SafepayError(Exception):
    """Safepay's API rejected a request — network errors surface as their
    own httpx exceptions instead, deliberately not caught here."""


async def create_tracker(amount: float, order_id: str, order_number: str) -> str:
    """Opens a payment session for `amount` (in whole PKR) and returns the
    tracker token used for everything downstream: the checkout URL and
    matching the eventual webhook back to this order."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{_api_base()}/order/payments/v3/",
            headers=_headers(),
            json={
                "merchant_api_key": settings.SAFEPAY_PUBLIC_KEY,
                "intent": "CYBERSOURCE",
                "mode": "payment",
                "currency": "PKR",
                # Safepay takes amounts in minor units (paisas), same as
                # Stripe cents.
                "amount": round(amount * 100),
            },
        )
        body = response.json()
        if response.status_code >= 400 or body.get("status", {}).get("errors"):
            raise SafepayError(f"Safepay tracker creation failed: {body}")
        tracker = body["data"]["tracker"]["token"]

        await client.post(
            f"{_api_base()}/order/payments/v3/{tracker}/metadata",
            headers=_headers(),
            json={"data": {"source": "wrenza-web", "order_id": order_id, "order_number": order_number}},
        )
        return tracker


async def create_passport_token() -> str:
    """Short-lived (1hr) token the hosted checkout page uses to authenticate
    itself — unrelated to the merchant secret, safe to hand to the browser
    via the redirect URL."""
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{_api_base()}/client/passport/v1/token",
            headers=_headers(),
            json={},
        )
        body = response.json()
        if response.status_code >= 400:
            raise SafepayError(f"Safepay passport creation failed: {body}")
        return body["data"]


def build_checkout_url(tracker: str, tbt: str, redirect_url: str, cancel_url: str) -> str:
    settings = get_settings()
    params = {
        "environment": settings.SAFEPAY_ENVIRONMENT,
        "tracker": tracker,
        "source": "hosted",
        "tbt": tbt,
        "redirect_url": redirect_url,
        "cancel_url": cancel_url,
    }
    query = httpx.QueryParams(params)
    return f"{_checkout_base()}/embedded?{query}"


def verify_webhook_signature(raw_body: bytes, signature: str) -> dict:
    """HMAC-SHA512 of the payload, keyed with the webhook shared secret.

    Safepay's own SDK examples re-serialize the parsed JSON before hashing
    rather than hashing the wire bytes directly, which only matters if their
    server's re-serialization differs from what it sent — so this tries the
    raw bytes first (the normal case: what was hashed is what was sent) and
    falls back to a compact re-encode. Either path still requires the real
    secret to produce a match, so trying both costs nothing security-wise.
    """
    secret = get_settings().SAFEPAY_WEBHOOK_SECRET.encode()

    def _hmac(payload: bytes) -> str:
        return hmac.new(secret, payload, hashlib.sha512).hexdigest()

    if hmac.compare_digest(_hmac(raw_body), signature):
        return json.loads(raw_body)

    parsed = json.loads(raw_body)
    compact = json.dumps(parsed, separators=(",", ":")).encode()
    if hmac.compare_digest(_hmac(compact), signature):
        return parsed

    raise SafepayError("Webhook signature verification failed")
