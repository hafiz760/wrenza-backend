from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, desc, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import Order, OrderItem, OrderStatus
from app.db.models.product import Product
from app.db.models.user import User, UserRole
from app.utils.casing import camelize


async def get_sales_summary(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total revenue and orders (only delivered/shipped)
    total_result = await db.execute(
        select(func.sum(Order.total), func.count(Order.id)).where(
            Order.status.in_([OrderStatus.DELIVERED.value, OrderStatus.SHIPPED.value])
        )
    )
    total_revenue, total_orders = total_result.one()

    # Today's stats
    today_result = await db.execute(
        select(func.sum(Order.total), func.count(Order.id)).where(
            Order.created_at >= today_start
        )
    )
    revenue_today, orders_today = today_result.one()

    total_revenue = float(total_revenue or 0)
    total_orders = total_orders or 0

    return camelize({
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "average_order_value": round(total_revenue / total_orders, 2) if total_orders > 0 else 0,
        "orders_today": orders_today or 0,
        "revenue_today": float(revenue_today or 0),
    })


async def get_best_sellers(db: AsyncSession, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(
            OrderItem.product_id,
            Product.name.label("product_name"),
            func.sum(OrderItem.quantity).label("total_sold"),
            func.sum(OrderItem.unit_price * OrderItem.quantity).label("total_revenue"),
        )
        .outerjoin(Product, OrderItem.product_id == Product.id)
        .group_by(OrderItem.product_id, Product.name)
        .order_by(desc("total_sold"))
        .limit(limit)
    )

    return camelize([
        {
            "product_id": str(row.product_id),
            "product_name": row.product_name or "Deleted Product",
            "total_sold": row.total_sold,
            "total_revenue": float(row.total_revenue),
        }
        for row in result.all()
    ])


async def get_stock_alerts(db: AsyncSession, threshold: int = 10) -> list[dict]:
    result = await db.execute(
        select(Product)
        .where(Product.is_active.is_(True), Product.stock <= threshold)
        .order_by(Product.stock)
    )

    return camelize([
        {
            "product_id": str(p.id),
            "product_name": p.name,
            "stock": p.stock,
            "slug": p.slug,
        }
        for p in result.scalars().all()
    ])


async def get_customer_metrics(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_customers = await db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.CUSTOMER)
    ) or 0

    new_this_month = await db.scalar(
        select(func.count(User.id)).where(
            User.role == UserRole.CUSTOMER, User.created_at >= month_start
        )
    ) or 0

    # Repeat customers (more than 1 order)
    repeat = await db.scalar(
        select(func.count())
        .select_from(
            select(Order.user_id)
            .group_by(Order.user_id)
            .having(func.count(Order.id) > 1)
            .subquery()
        )
    ) or 0

    # Average lifetime value
    avg_ltv_result = await db.scalar(
        select(func.avg(Order.total))
        .where(Order.status != OrderStatus.CANCELLED.value)
    )

    return camelize({
        "total_customers": total_customers,
        "new_customers_this_month": new_this_month,
        "repeat_customers": repeat,
        "average_lifetime_value": round(float(avg_ltv_result or 0), 2),
    })
