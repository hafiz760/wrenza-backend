from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AdminUser, DbSession
from app.db.models.user import User
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.wishlist import Wishlist
from app.schemas.user import AdminUserUpdate
from app.utils.pagination import paginate
from app.utils.casing import camelize

router = APIRouter(prefix="/users", tags=["Admin - Users"])


@router.get("")
async def list_users(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100, alias="pageSize"),
    search: str | None = None,
):
    query = select(User).order_by(desc(User.created_at))

    if search:
        query = query.where(
            User.email.ilike(f"%{search}%")
            | User.first_name.ilike(f"%{search}%")
            | User.last_name.ilike(f"%{search}%")
        )

    result = await paginate(query, page, pageSize, db)
    result["items"] = [
        {
            "id": str(u.id),
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in result["items"]
    ]
    return camelize(result)


@router.get("/{user_id}")
async def get_user_detail(user_id: str, admin: AdminUser, db: DbSession):
    """Return a customer's profile and related storefront data for admins."""
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.addresses),
            selectinload(User.wishlists)
            .selectinload(Wishlist.product)
            .selectinload(Product.images),
        )
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    orders_result = await db.execute(
        select(Order).where(Order.user_id == user.id).order_by(desc(Order.created_at))
    )
    orders = orders_result.scalars().all()

    wishlist = []
    for entry in user.wishlists:
        product = entry.product
        if not product:
            continue
        featured = next((image for image in product.images if image.is_featured), None)
        image = featured or (product.images[0] if product.images else None)
        wishlist.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                "slug": product.slug,
                "price": float(product.price),
                "is_active": product.is_active,
                "image_url": image.url if image else None,
                "added_at": entry.created_at.isoformat() if entry.created_at else None,
            }
        )

    return camelize(
        {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "avatar": user.avatar,
            "role": user.role.value if hasattr(user.role, "value") else user.role,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "addresses": [
                {
                    "id": str(address.id),
                    "label": address.label,
                    "street": address.street,
                    "city": address.city,
                    "state": address.state,
                    "postal_code": address.postal_code,
                    "country": address.country,
                    "is_default": address.is_default,
                }
                for address in user.addresses
            ],
            "wishlist": wishlist,
            "orders": [
                {
                    "id": str(order.id),
                    "order_number": order.order_number,
                    "status": order.status,
                    "payment_method": order.payment_method,
                    "payment_status": order.payment_status,
                    "total": float(order.total),
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                }
                for order in orders
            ],
        }
    )


@router.put("/{user_id}")
async def update_user(user_id: str, data: AdminUserUpdate, admin: AdminUser, db: DbSession):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    return camelize({
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    })
