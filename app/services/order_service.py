from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, desc, func, or_
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models.activity_log import ActivityLog
from app.db.models.order import Order, OrderItem, OrderStatus, PaymentStatus
from app.db.models.attribute import AttributeTerm
from app.db.models.product import Product
from app.db.models.variation import ProductVariation, VariationAttributeValue
from app.db.models.user import Address, User
from app.utils.cache import cache_delete_pattern
from app.services import settings_service
from app.services.product_service import _pick_featured, _product_to_list_out
from app.schemas.order import (
    OrderStatusLogEntry,
    CheckoutRequest,
    OrderCreate,
    OrderOut,
    OrderItemOut,
    OrderStatusUpdate,
)
from app.schemas.common import PaginatedResponse
from app.tasks.queue import enqueue


def _order_to_out(order: Order) -> OrderOut:
    items = [
        OrderItemOut(
            product=item.product_snapshot,
            quantity=item.quantity,
        )
        for item in order.items
    ]

    name_parts = [order.guest_first_name, order.guest_last_name]
    customer_name = " ".join(p for p in name_parts if p) or None

    return OrderOut(
        id=str(order.id),
        order_number=order.order_number,
        customer_name=customer_name,
        email=order.email,
        phone=order.phone,
        notes=order.notes,
        items=items,
        status=order.status,
        subtotal=float(order.subtotal),
        shipping=float(order.shipping),
        tax=float(order.tax),
        discount=float(order.discount),
        total=float(order.total),
        shipping_address=order.shipping_address,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        tracking_number=order.tracking_number,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


async def _pricing(db: AsyncSession, subtotal: Decimal) -> tuple[Decimal, Decimal]:
    """Shipping and tax for a cart, from live store settings.

    Both used to be hardcoded constants with no admin control at all. Tax
    applies to (subtotal + shipping) together, not the subtotal alone — the
    store's own choice, not a platform default.
    """
    settings = await settings_service.get_or_create(db)

    shipping = (
        Decimal("0")
        if subtotal >= Decimal(str(settings.free_shipping_threshold))
        else Decimal(str(settings.shipping_cost))
    )
    taxable = subtotal + shipping
    tax = (taxable * Decimal(str(settings.tax_rate)) / Decimal("100")).quantize(
        Decimal("0.01")
    )
    return shipping, tax


async def _reserve_line_item(db: AsyncSession, item_data) -> tuple[dict, Decimal]:
    """Validate one checkout line, reserve its stock, and build its snapshot.

    Single source of truth for both the guest checkout and the authenticated
    order path — they previously carried identical copies of this logic, which
    is how the two drifted apart in the first place.

    Stock is taken from the variation for variable products and from the product
    itself for simple ones.
    """
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(Product.id == item_data.product_id, Product.is_active.is_(True))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=400, detail=f"Product {item_data.product_id} not found"
        )

    variation_id = getattr(item_data, "variation_id", None)

    if product.kind == "variable":
        if not variation_id:
            raise HTTPException(
                status_code=422,
                detail=f"'{product.name}' is a variable product — variationId is required.",
            )
        variation = await db.scalar(
            select(ProductVariation).where(
                ProductVariation.id == variation_id,
                ProductVariation.product_id == product.id,
            )
        )
        if not variation:
            raise HTTPException(
                status_code=422,
                detail=f"Variation {variation_id} does not belong to '{product.name}'.",
            )
        if not variation.is_active:
            raise HTTPException(
                status_code=422, detail=f"That option of '{product.name}' is unavailable."
            )
        stock_holder = variation
        unit_price = Decimal(str(variation.price))
    else:
        if variation_id:
            raise HTTPException(
                status_code=422,
                detail=f"'{product.name}' is a simple product — do not send variationId.",
            )
        stock_holder = product
        unit_price = Decimal(str(product.price))

    if stock_holder.stock < item_data.quantity:
        raise HTTPException(
            status_code=400, detail=f"Insufficient stock for {product.name}"
        )

    # by_alias so the snapshot is camelCase like every other payload. It is
    # stored as an opaque dict, so nothing downstream would convert it later.
    snapshot = _product_to_list_out(product).model_dump(mode="json", by_alias=True)
    if product.kind == "variable":
        terms = await db.execute(
            select(AttributeTerm)
            .join(
                VariationAttributeValue,
                VariationAttributeValue.term_id == AttributeTerm.id,
            )
            .options(selectinload(AttributeTerm.attribute))
            .where(VariationAttributeValue.variation_id == stock_holder.id)
        )
        # Recorded on the order so it stays readable after the variation is gone
        snapshot["variation"] = {
            "id": str(stock_holder.id),
            "sku": stock_holder.sku,
            "attributes": {t.attribute.name: t.value for t in terms.scalars().all()},
        }

        # The purchased variation's own photo, not a bare product image or
        # `_split_images`'s generic "first variation" fallback. A customer who
        # bought Tan must not see Blue's photo on their order just because
        # Blue happens to sit first in the variation list.
        if stock_holder.images:
            v_featured, v_gallery = _pick_featured(stock_holder.images)
            snapshot["featuredImage"] = (
                v_featured.model_dump(mode="json", by_alias=True)
                if v_featured
                else None
            )
            snapshot["images"] = [
                img.model_dump(mode="json", by_alias=True) for img in v_gallery
            ]

    stock_holder.stock -= item_data.quantity

    return (
        {
            "product_id": product.id,
            "variation_id": variation_id,
            "product_snapshot": snapshot,
            "quantity": item_data.quantity,
            "unit_price": float(unit_price),
        },
        unit_price * item_data.quantity,
    )


async def _generate_order_number(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    count = await db.scalar(
        select(func.count(Order.id)).where(Order.order_number.like(f"WZ-{year}-%"))
    )
    return f"WZ-{year}-{(count or 0) + 1:03d}"


async def create_order(
    db: AsyncSession, user_id: str, data: OrderCreate, redis: Redis | None = None
) -> OrderOut:
    # Resolve shipping address
    shipping_address: dict
    if data.address_id:
        address = await db.scalar(
            select(Address).where(
                Address.id == data.address_id, Address.user_id == user_id
            )
        )
        if not address:
            raise HTTPException(status_code=400, detail="Address not found")
        shipping_address = {
            "id": str(address.id),
            "label": address.label,
            "street": address.street,
            "city": address.city,
            "state": address.state,
            "postalCode": address.postal_code,
            "country": address.country,
            "isDefault": address.is_default,
        }
    elif data.shipping_address:
        shipping_address = {
            "label": data.shipping_address.label,
            "street": data.shipping_address.street,
            "city": data.shipping_address.city,
            "state": data.shipping_address.state,
            "postalCode": data.shipping_address.postal_code,
            "country": data.shipping_address.country,
            "isDefault": False,
        }
    else:
        raise HTTPException(status_code=400, detail="Shipping address is required")

    # Validate products and calculate subtotal
    subtotal = Decimal("0")
    order_items = []

    for item_data in data.items:
        line, line_total = await _reserve_line_item(db, item_data)
        order_items.append(line)
        subtotal += line_total

    shipping, tax = await _pricing(db, subtotal)

    # Apply discount
    discount = Decimal("0")
    if data.discount_code:
        from app.services.promotion_service import validate_discount

        discount_result = await validate_discount(
            db, data.discount_code, float(subtotal)
        )
        if discount_result:
            discount = Decimal(str(discount_result["amount"]))

    total = subtotal + shipping + tax - discount

    # Generate order number
    order_number = await _generate_order_number(db)

    # Create order
    order = Order(
        user_id=user_id,
        order_number=order_number,
        status=OrderStatus.PENDING,
        subtotal=float(subtotal),
        shipping=float(shipping),
        tax=float(tax),
        discount=float(discount),
        total=float(total),
        shipping_address=shipping_address,
        payment_method="Cash on Delivery",
        discount_code=data.discount_code,
        phone=data.phone,
        notes=data.notes,
    )
    db.add(order)
    await db.flush()

    # Create order items
    for item in order_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                variation_id=item["variation_id"],
                product_snapshot=item["product_snapshot"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
        )

    await db.commit()
    await _invalidate_product_cache(redis)

    # Queued after the commit: the job loads the order by id, so it must exist
    # before the worker can pick it up.
    await enqueue("send_order_confirmation", str(order.id))

    # Refresh with relationships
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = result.scalar_one()

    return _order_to_out(order)


async def _build_order(
    db: AsyncSession,
    data: CheckoutRequest,
    user_id: str | None,
    payment_method: str,
) -> Order:
    """Shared by every checkout path — Cash on Delivery and Safepay both
    reserve stock and price the order identically. Flushed but not
    committed: the caller decides when this becomes durable, since the
    Safepay path needs the order's id before it can even talk to Safepay."""

    subtotal = Decimal("0")
    order_items = []

    for item_data in data.items:
        line, line_total = await _reserve_line_item(db, item_data)
        order_items.append(line)
        subtotal += line_total

    shipping, tax = await _pricing(db, subtotal)

    discount = Decimal("0")
    if data.discount_code:
        from app.services.promotion_service import validate_discount

        discount_result = await validate_discount(
            db, data.discount_code, float(subtotal)
        )
        if discount_result:
            discount = Decimal(str(discount_result["amount"]))

    total = subtotal + shipping + tax - discount

    # Build shipping address (camelCase keys for frontend)
    shipping_address = {
        "firstName": data.first_name,
        "lastName": data.last_name,
        "street": data.street,
        "city": data.city,
        "state": data.state,
        "postalCode": data.postal_code,
        "country": "Pakistan",
    }

    order_number = await _generate_order_number(db)

    order = Order(
        user_id=user_id,
        order_number=order_number,
        status=OrderStatus.PENDING.value,
        subtotal=float(subtotal),
        shipping=float(shipping),
        tax=float(tax),
        discount=float(discount),
        total=float(total),
        shipping_address=shipping_address,
        payment_method=payment_method,
        discount_code=data.discount_code,
        phone=data.phone,
        email=data.email,
        guest_first_name=data.first_name if not user_id else None,
        guest_last_name=data.last_name if not user_id else None,
        notes=data.notes,
    )
    db.add(order)
    await db.flush()

    for item in order_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item["product_id"],
                variation_id=item["variation_id"],
                product_snapshot=item["product_snapshot"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
            )
        )

    return order


async def _refetch(db: AsyncSession, order_id) -> Order:
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    return result.scalar_one()


async def create_checkout_order(
    db: AsyncSession,
    data: CheckoutRequest,
    user_id: str | None = None,
    redis: Redis | None = None,
) -> OrderOut:
    """Unified Cash on Delivery checkout for both guest and authenticated
    users. Matches the frontend checkout form: email, phone, name, address,
    items."""

    order = await _build_order(db, data, user_id, "Cash on Delivery")
    await db.commit()
    await _invalidate_product_cache(redis)

    await enqueue("send_order_confirmation", str(order.id))

    order = await _refetch(db, order.id)
    return _order_to_out(order)


async def create_safepay_checkout_order(
    db: AsyncSession,
    data: CheckoutRequest,
    user_id: str | None = None,
    redis: Redis | None = None,
) -> tuple[OrderOut, str]:
    """Reserves stock and prices the order exactly like Cash on Delivery,
    then opens a Safepay payment session for it and returns the hosted
    checkout URL to redirect the customer to.

    Commits immediately (as `unpaid`) so the webhook has something to find
    when Safepay calls back, possibly minutes later in a separate request —
    but does NOT send the order-confirmation email yet. `send_safepay_paid`
    fires that once the webhook confirms the charge; an abandoned checkout
    must not look like a placed order to the customer.
    """
    from app.services import safepay_service

    store_settings = await settings_service.get_or_create(db)
    if not store_settings.safepay_enabled:
        raise HTTPException(status_code=403, detail="Online payment is currently unavailable.")

    order = await _build_order(db, data, user_id, "Safepay")

    try:
        tracker = await safepay_service.create_tracker(
            float(order.total), str(order.id), order.order_number
        )
        tbt = await safepay_service.create_passport_token()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=502, detail="Could not start payment session. Please try again."
        ) from exc

    order.payment_reference = tracker
    await db.commit()
    await _invalidate_product_cache(redis)

    order = await _refetch(db, order.id)

    frontend_url = get_settings().FRONTEND_URL.rstrip("/")
    checkout_url = safepay_service.build_checkout_url(
        tracker=tracker,
        tbt=tbt,
        redirect_url=f"{frontend_url}/checkout/success?order={order.order_number}",
        cancel_url=f"{frontend_url}/checkout/cancel?order={order.order_number}",
    )

    return _order_to_out(order), checkout_url


async def mark_safepay_payment(
    db: AsyncSession, tracker: str, succeeded: bool
) -> Order | None:
    """Applies a Safepay webhook outcome to the order it belongs to.

    Idempotent by design — Safepay retries a webhook until it gets a 200, so
    this may run more than once for the same event. Only touches an order
    still `unpaid`; a second `payment.succeeded` for an already-paid order,
    or a late `payment.failed` after it already succeeded, is a no-op rather
    than a state flip.
    """
    order = await db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.payment_reference == tracker)
    )
    if order is None or order.payment_status != PaymentStatus.UNPAID.value:
        return order

    order.payment_status = (
        PaymentStatus.PAID.value if succeeded else PaymentStatus.FAILED.value
    )
    await db.commit()

    if succeeded:
        await enqueue("send_order_confirmation", str(order.id))

    return await _refetch(db, order.id)


async def get_user_orders(db: AsyncSession, user_id: str) -> list[OrderOut]:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user_id)
        .order_by(desc(Order.created_at))
    )
    return [_order_to_out(o) for o in result.scalars().all()]


async def get_order_detail(db: AsyncSession, user_id: str, order_id: str) -> OrderOut:
    result = await db.execute(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_to_out(order)


# Valid status transitions
VALID_TRANSITIONS = {
    OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
    OrderStatus.CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
    OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
    OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
    OrderStatus.DELIVERED: [],
    OrderStatus.CANCELLED: [],
}


async def _invalidate_product_cache(redis: Redis | None) -> None:
    """Drop cached product payloads after a stock movement.

    Stock is part of the cached product detail, and detail is held for two
    hours. Without this a sold-out product keeps advertising itself as in
    stock until the entry expires, which is how a shop oversells.
    """
    if redis is not None:
        await cache_delete_pattern(redis, "products:*")


async def _restore_stock(db: AsyncSession, order: Order) -> None:
    """Return a cancelled order's units to whatever they were taken from.

    Without this, cancelling destroys inventory permanently — the stock was
    deducted at checkout and nothing ever gave it back.
    """
    for item in order.items:
        if item.variation_id:
            holder = await db.scalar(
                select(ProductVariation).where(
                    ProductVariation.id == item.variation_id
                )
            )
        else:
            holder = await db.scalar(
                select(Product).where(Product.id == item.product_id)
            )
        # The product or variation may have been deleted since the order was
        # placed; there is simply nothing to restore in that case.
        if holder is not None:
            holder.stock += item.quantity


async def update_order_status(
    db: AsyncSession,
    order_id: str,
    data: OrderStatusUpdate,
    admin_id: str | None = None,
) -> OrderOut:
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    new_status = OrderStatus(data.status)
    current_status = OrderStatus(order.status)

    if new_status not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status.value} to {new_status.value}",
        )

    if new_status == OrderStatus.CANCELLED:
        await _restore_stock(db, order)

    order.status = new_status.value
    if data.tracking_number:
        order.tracking_number = data.tracking_number

    # Nothing else records when an order moved between statuses — `status` is
    # simply overwritten each time — so the detail page's timeline is built
    # entirely from these rows.
    db.add(
        ActivityLog(
            user_id=admin_id,
            action="order_status_changed",
            entity="order",
            entity_id=str(order.id),
            details={"from": current_status.value, "to": new_status.value},
        )
    )

    await db.commit()

    # The task filters to shipped/delivered — sending on every internal
    # transition trains customers to stop opening these.
    await enqueue("send_order_status_update", str(order.id), new_status.value)

    # `updated_at` carries onupdate=func.now(), so it is server-generated and
    # expired by the UPDATE; reading it without refreshing lazy-loads outside
    # the async greenlet.
    await db.refresh(order)
    return _order_to_out(order)


async def cancel_order(
    db: AsyncSession,
    order_id: str,
    user_id: str | None = None,
    admin_id: str | None = None,
    redis: Redis | None = None,
) -> OrderOut:
    """Cancel an order and return its stock.

    `user_id` scopes the lookup for the customer-facing route and doubles as
    the log's actor there; the admin route has no scoping id, so it passes
    `admin_id` for the same purpose instead.
    """
    query = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    if user_id is not None:
        query = query.where(Order.user_id == user_id)

    order = (await db.execute(query)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    current_status = OrderStatus(order.status)
    if OrderStatus.CANCELLED not in VALID_TRANSITIONS.get(current_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"An order that is already {current_status.value} cannot be cancelled.",
        )

    await _restore_stock(db, order)
    order.status = OrderStatus.CANCELLED.value
    db.add(
        ActivityLog(
            user_id=admin_id or user_id,
            action="order_status_changed",
            entity="order",
            entity_id=str(order.id),
            details={"from": current_status.value, "to": OrderStatus.CANCELLED.value},
        )
    )
    await db.commit()
    await _invalidate_product_cache(redis)

    await enqueue("send_order_cancelled", str(order.id))

    await db.refresh(order)
    return _order_to_out(order)


async def delete_order(
    db: AsyncSession, order_id: str, redis: Redis | None = None, admin_id: str | None = None
) -> None:
    """Permanently remove an order and its items.

    For cleaning up test orders, not a customer-facing action — there is no
    equivalent route on the customer or public routers. Unlike cancelling,
    this leaves no record behind; the activity log entry is written before
    the delete so there is at least a trace of what was removed and by whom.

    Stock is restored first, unless the order was already cancelled and so
    already gave its stock back — otherwise deleting a pending test order
    would permanently understate inventory.
    """
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status != OrderStatus.CANCELLED.value:
        await _restore_stock(db, order)

    db.add(
        ActivityLog(
            user_id=admin_id,
            action="order_deleted",
            entity="order",
            entity_id=str(order.id),
            details={"orderNumber": order.order_number},
        )
    )

    await db.delete(order)
    await db.commit()
    await _invalidate_product_cache(redis)


async def get_order_admin(db: AsyncSession, order_id: str) -> OrderOut:
    """Single order for admin — unlike get_order_detail, not scoped to a user."""
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    out = _order_to_out(order)
    out.status_history = await _status_history(db, order_id)
    return out


async def _status_history(db: AsyncSession, order_id: str) -> list[OrderStatusLogEntry]:
    """Logged transitions for the timeline, oldest first.

    Outer-joined against `User` rather than a second round trip per row: an
    admin account can be deleted later, and the log should still read rather
    than 404 on a name lookup.
    """
    rows = await db.execute(
        select(ActivityLog, User)
        .outerjoin(User, ActivityLog.user_id == User.id)
        .where(ActivityLog.entity == "order", ActivityLog.entity_id == order_id)
        .order_by(ActivityLog.created_at)
    )
    return [
        OrderStatusLogEntry(
            from_status=(log.details or {}).get("from"),
            to_status=(log.details or {}).get("to", ""),
            changed_at=log.created_at,
            changed_by=f"{user.first_name} {user.last_name}".strip() if user else None,
        )
        for log, user in rows.all()
    ]


async def get_all_orders(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> PaginatedResponse[OrderOut]:
    from app.utils.pagination import paginate

    query = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(desc(Order.created_at))
    )

    if status_filter:
        query = query.where(Order.status == status_filter)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(
                Order.order_number.ilike(term),
                Order.email.ilike(term),
                Order.phone.ilike(term),
                Order.guest_first_name.ilike(term),
                Order.guest_last_name.ilike(term),
            )
        )
    if date_from:
        query = query.where(Order.created_at >= date_from)
    if date_to:
        query = query.where(Order.created_at <= date_to)

    result = await paginate(query, page, page_size, db)
    items = [_order_to_out(o) for o in result["items"]]

    return PaginatedResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )
