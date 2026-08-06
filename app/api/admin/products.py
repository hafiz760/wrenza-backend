from typing import Literal

from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession, RedisClient
from app.schemas.common import MessageResponse
from app.schemas.product import ProductCreate, ProductImageCreate, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Admin - Products"])


@router.get("")
async def list_products(
    db: DbSession,
    admin: AdminUser,
    status: Literal["active", "trashed", "all"] = "active",
    search: str | None = None,
    page: int = 1,
    pageSize: int = 20,
):
    """Products for the admin panel.

    Unlike the storefront list this can return inactive products — "deleting" a
    product only clears `is_active`, so without `status=trashed` there would be
    no way to find or restore one.
    """
    return await product_service.list_products_admin(
        db, status=status, search=search, page=page, page_size=pageSize
    )


@router.get("/counts")
async def product_counts(db: DbSession, admin: AdminUser):
    """Active and trashed totals, for the admin's tab badges."""
    return await product_service.count_by_status(db)


@router.post("")
async def create_product(data: ProductCreate, admin: AdminUser, db: DbSession, redis: RedisClient):
    return await product_service.create_product(db, redis, data)


@router.put("/{product_id}")
async def update_product(
    product_id: str, data: ProductUpdate, admin: AdminUser, db: DbSession, redis: RedisClient
):
    return await product_service.update_product(db, redis, product_id, data)


@router.post("/{product_id}/restore")
async def restore_product(
    product_id: str, admin: AdminUser, db: DbSession, redis: RedisClient
):
    """Bring a trashed product back to the storefront."""
    return await product_service.restore_product(db, redis, product_id)


@router.delete("/{product_id}/permanent", response_model=MessageResponse)
async def purge_product(
    product_id: str, admin: AdminUser, db: DbSession, redis: RedisClient
):
    """Delete a trashed product for good.

    Past orders are unaffected — each order line keeps its own snapshot of the
    product, and the foreign key is ON DELETE SET NULL.
    """
    await product_service.purge_product(db, redis, product_id)
    return MessageResponse(message="Product permanently deleted")


@router.delete("/{product_id}")
async def delete_product(product_id: str, admin: AdminUser, db: DbSession, redis: RedisClient):
    """Move a product to trash. Reversible via `/restore`."""
    await product_service.delete_product(db, redis, product_id)
    return {"message": "Product deleted"}


class ProductImageAdd(ProductImageCreate):
    is_featured: bool = False


@router.post("/{product_id}/images")
async def add_product_image(
    product_id: str,
    data: ProductImageAdd,
    admin: AdminUser,
    db: DbSession,
    redis: RedisClient,
):
    """Add an image to the product gallery, optionally as the hero."""
    return await product_service.add_product_image(db, redis, product_id, data)


@router.delete("/{product_id}/images/{image_id}", response_model=MessageResponse)
async def delete_product_image(
    product_id: str,
    image_id: str,
    admin: AdminUser,
    db: DbSession,
    redis: RedisClient,
):
    await product_service.delete_product_image(db, redis, product_id, image_id)
    return MessageResponse(message="Image deleted")
