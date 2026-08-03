from fastapi import APIRouter

from app.core.deps import DbSession, OptionalUser
from app.schemas.order import CheckoutRequest
from app.services import order_service

router = APIRouter(tags=["Checkout"])


@router.post("/checkout")
async def checkout(data: CheckoutRequest, db: DbSession, user: OptionalUser):
    """Place an order — works for both guest and logged-in users.
    If a valid Bearer token is provided, the order is linked to the user account."""
    user_id = user.id if user else None
    return await order_service.create_checkout_order(db, data, user_id=user_id)
