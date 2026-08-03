from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession, RedisClient
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Admin - Products"])


@router.get("")
async def list_products(
    db: DbSession,
    redis: RedisClient,
    admin: AdminUser,
    page: int = 1,
    pageSize: int = 20,
):
    return await product_service.list_products(db, redis, page=page, page_size=pageSize)


@router.post("")
async def create_product(data: ProductCreate, admin: AdminUser, db: DbSession, redis: RedisClient):
    return await product_service.create_product(db, redis, data)


@router.put("/{product_id}")
async def update_product(
    product_id: str, data: ProductUpdate, admin: AdminUser, db: DbSession, redis: RedisClient
):
    return await product_service.update_product(db, redis, product_id, data)


@router.delete("/{product_id}")
async def delete_product(product_id: str, admin: AdminUser, db: DbSession, redis: RedisClient):
    await product_service.delete_product(db, redis, product_id)
    return {"message": "Product deleted"}
