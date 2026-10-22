from fastapi import APIRouter

from app.core.deps import DbSession, OptionalUser, RedisClient
from app.schemas.order import CheckoutRequest, SafepayInitiateOut
from app.schemas.promotion import DiscountValidationOut, DiscountValidationRequest
from app.services import order_service
from app.services.promotion_service import validate_discount

router = APIRouter(tags=["Checkout"])


@router.post("/checkout/discount/validate", response_model=DiscountValidationOut)
async def validate_checkout_discount(data: DiscountValidationRequest, db: DbSession):
    """Preview a coupon against the current cart subtotal."""
    result = await validate_discount(db, data.code, data.subtotal)
    if not result:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail="This discount code is invalid, expired, used up, or the order minimum is not met.",
        )
    return result


@router.post("/checkout")
async def checkout(
    data: CheckoutRequest, db: DbSession, user: OptionalUser, redis: RedisClient
):
    """Place a Cash on Delivery order — works for both guest and logged-in
    users. If a valid Bearer token is provided, the order is linked to the
    user account."""
    user_id = user.id if user else None
    return await order_service.create_checkout_order(db, data, user_id=user_id, redis=redis)


@router.post("/checkout/safepay", response_model=SafepayInitiateOut)
async def checkout_safepay(
    data: CheckoutRequest, db: DbSession, user: OptionalUser, redis: RedisClient
):
    """Place an order paid via Safepay — same shape as `/checkout`, but
    returns a hosted checkout URL to redirect the customer to instead of a
    finished order. The order exists immediately (as `unpaid`); the webhook
    at `/webhooks/safepay` is what confirms payment."""
    user_id = user.id if user else None
    order, checkout_url = await order_service.create_safepay_checkout_order(
        db, data, user_id=user_id, redis=redis
    )
    return SafepayInitiateOut(
        order_id=order.id, order_number=order.order_number, checkout_url=checkout_url
    )
