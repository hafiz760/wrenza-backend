from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.order import Order, OrderItem, OrderStatus
from app.db.models.product import Product
from app.db.models.user import Address
from app.services.product_service import _product_to_list_out
from app.schemas.order import (
    CheckoutRequest,
    OrderCreate,
    OrderOut,
    OrderItemOut,
    OrderStatusUpdate,
)
from app.schemas.common import PaginatedResponse

FREE_SHIPPING_THRESHOLD = 5000  # PKR
SHIPPING_COST = 250  # PKR


def _order_to_out(order: Order) -> OrderOut:
    items = [
        OrderItemOut(
            product=item.product_snapshot,
            quantity=item.quantity,
            size=item.size,
            color=item.color,
        )
        for item in order.items
    ]

    return OrderOut(
        id=str(order.id),
        order_number=order.order_number,
        items=items,
        status=order.status,
        subtotal=float(order.subtotal),
        shipping=float(order.shipping),
        discount=float(order.discount),
        total=float(order.total),
        shipping_address=order.shipping_address,
        payment_method=order.payment_method,
        tracking_number=order.tracking_number,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


async def _generate_order_number(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    count = await db.scalar(
        select(func.count(Order.id)).where(Order.order_number.like(f"KK-{year}-%"))
    )
    return f"KK-{year}-{(count or 0) + 1:03d}"


async def create_order(db: AsyncSession, user_id: str, data: OrderCreate) -> OrderOut:
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
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.images), selectinload(Product.category))
            .where(Product.id == item_data.product_id, Product.is_active.is_(True))
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item_data.product_id} not found",
            )

        if product.stock < item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}",
            )

        unit_price = Decimal(str(product.price))
        subtotal += unit_price * item_data.quantity

        # Create product snapshot for order history
        snapshot = _product_to_list_out(product).model_dump()

        order_items.append(
            {
                "product_id": product.id,
                "product_snapshot": snapshot,
                "quantity": item_data.quantity,
                "size": item_data.size,
                "color": item_data.color,
                "unit_price": float(unit_price),
            }
        )

        # Deduct stock
        product.stock -= item_data.quantity

    # Calculate shipping
    shipping = (
        Decimal("0")
        if subtotal >= FREE_SHIPPING_THRESHOLD
        else Decimal(str(SHIPPING_COST))
    )

    # Apply discount
    discount = Decimal("0")
    if data.discount_code:
        from app.services.promotion_service import validate_discount

        discount_result = await validate_discount(
            db, data.discount_code, float(subtotal)
        )
        if discount_result:
            discount = Decimal(str(discount_result["amount"]))

    total = subtotal + shipping - discount

    # Generate order number
    order_number = await _generate_order_number(db)

    # Create order
    order = Order(
        user_id=user_id,
        order_number=order_number,
        status=OrderStatus.PENDING,
        subtotal=float(subtotal),
        shipping=float(shipping),
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
                product_snapshot=item["product_snapshot"],
                quantity=item["quantity"],
                size=item["size"],
                color=item["color"],
                unit_price=item["unit_price"],
            )
        )

    await db.commit()

    # Refresh with relationships
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = result.scalar_one()

    return _order_to_out(order)


async def create_checkout_order(
    db: AsyncSession, data: CheckoutRequest, user_id: str | None = None
) -> OrderOut:
    """Unified checkout for both guest and authenticated users.
    Matches the frontend checkout form: email, phone, name, address, items."""

    # Validate products and calculate subtotal
    subtotal = Decimal("0")
    order_items = []

    for item_data in data.items:
        result = await db.execute(
            select(Product)
            .options(selectinload(Product.images), selectinload(Product.category))
            .where(Product.id == item_data.product_id, Product.is_active.is_(True))
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item_data.product_id} not found",
            )

        if product.stock < item_data.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {product.name}",
            )

        unit_price = Decimal(str(product.price))
        subtotal += unit_price * item_data.quantity

        snapshot = _product_to_list_out(product).model_dump()

        order_items.append(
            {
                "product_id": product.id,
                "product_snapshot": snapshot,
                "quantity": item_data.quantity,
                "size": item_data.size,
                "color": item_data.color,
                "unit_price": float(unit_price),
            }
        )

        # Deduct stock
        product.stock -= item_data.quantity

    # Calculate shipping
    shipping = (
        Decimal("0")
        if subtotal >= FREE_SHIPPING_THRESHOLD
        else Decimal(str(SHIPPING_COST))
    )

    # Apply discount
    discount = Decimal("0")
    if data.discount_code:
        from app.services.promotion_service import validate_discount

        discount_result = await validate_discount(
            db, data.discount_code, float(subtotal)
        )
        if discount_result:
            discount = Decimal(str(discount_result["amount"]))

    total = subtotal + shipping - discount

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
        discount=float(discount),
        total=float(total),
        shipping_address=shipping_address,
        payment_method="Cash on Delivery",
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
                product_snapshot=item["product_snapshot"],
                quantity=item["quantity"],
                size=item["size"],
                color=item["color"],
                unit_price=item["unit_price"],
            )
        )

    await db.commit()

    # Re-fetch with relationships
    result = await db.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
    )
    order = result.scalar_one()

    return _order_to_out(order)


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


async def update_order_status(
    db: AsyncSession, order_id: str, data: OrderStatusUpdate
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

    order.status = new_status.value
    if data.tracking_number:
        order.tracking_number = data.tracking_number

    await db.commit()
    return _order_to_out(order)


async def get_all_orders(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: str | None = None,
) -> PaginatedResponse[OrderOut]:
    from app.utils.pagination import paginate

    query = (
        select(Order)
        .options(selectinload(Order.items))
        .order_by(desc(Order.created_at))
    )

    if status_filter:
        query = query.where(Order.status == status_filter)

    result = await paginate(query, page, page_size, db)
    items = [_order_to_out(o) for o in result["items"]]

    return PaginatedResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )
