import structlog
from fastapi import APIRouter, Header, HTTPException, Request

from app.core.deps import DbSession
from app.services import order_service, safepay_service

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = structlog.get_logger()


@router.post("/safepay")
async def safepay_webhook(
    request: Request,
    db: DbSession,
    x_sfpy_signature: str | None = Header(default=None),
):
    """Safepay's async confirmation of a payment's outcome — the customer's
    browser redirect back to the storefront is never trusted for this, only
    this webhook is. Always returns 200 once the signature checks out, even
    for an event type or tracker we don't recognise: a non-200 makes Safepay
    retry indefinitely, and there is nothing to retry into existing here."""
    raw_body = await request.body()

    if not x_sfpy_signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    try:
        event = safepay_service.verify_webhook_signature(raw_body, x_sfpy_signature)
    except safepay_service.SafepayError:
        logger.warning("Safepay webhook signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event.get("type")
    data = event.get("data", {})
    tracker = data.get("tracker")

    if not tracker:
        return {"status": "ignored"}

    if event_type == "payment.succeeded":
        await order_service.mark_safepay_payment(db, tracker, succeeded=True)
    elif event_type == "payment.failed":
        await order_service.mark_safepay_payment(db, tracker, succeeded=False)
    # Other event types (authorization.*, void.*, subscription.*) are
    # acknowledged but not acted on — Wrenza doesn't use holds/subscriptions.

    return {"status": "ok"}
