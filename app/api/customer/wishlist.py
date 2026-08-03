from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import CurrentUser, DbSession
from app.db.models.product import Product
from app.db.models.wishlist import Wishlist
from app.schemas.common import MessageResponse
from app.services.product_service import _product_to_list_out

router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get("")
async def get_wishlist(user: CurrentUser, db: DbSession):
    result = await db.execute(
        select(Wishlist)
        .options(selectinload(Wishlist.product).selectinload(Product.images))
        .where(Wishlist.user_id == user.id)
    )
    wishlists = result.scalars().all()

    products = []
    for w in wishlists:
        if w.product and w.product.is_active:
            products.append(_product_to_list_out(w.product))

    return products


@router.post("/{product_id}", response_model=MessageResponse)
async def add_to_wishlist(product_id: str, user: CurrentUser, db: DbSession):
    # Verify product exists
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.is_active.is_(True))
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if already in wishlist
    existing = await db.scalar(
        select(Wishlist).where(
            Wishlist.user_id == user.id, Wishlist.product_id == product_id
        )
    )
    if existing:
        return MessageResponse(message="Already in wishlist")

    db.add(Wishlist(user_id=user.id, product_id=product_id))
    await db.commit()
    return MessageResponse(message="Added to wishlist")


@router.delete("/{product_id}", response_model=MessageResponse)
async def remove_from_wishlist(product_id: str, user: CurrentUser, db: DbSession):
    item = await db.scalar(
        select(Wishlist).where(
            Wishlist.user_id == user.id, Wishlist.product_id == product_id
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not in wishlist")

    await db.delete(item)
    await db.commit()
    return MessageResponse(message="Removed from wishlist")
