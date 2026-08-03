from fastapi import APIRouter, Query

from app.core.deps import DbSession, RedisClient
from app.services import product_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("")
async def list_products(
    db: DbSession,
    redis: RedisClient,
    category: str | None = None,
    minPrice: float | None = Query(None, alias="minPrice"),
    maxPrice: float | None = Query(None, alias="maxPrice"),
    productType: str | None = Query(None, alias="productType"),
    material: str | None = None,
    leatherType: str | None = Query(None, alias="leatherType"),
    sizes: str | None = None,
    colors: str | None = None,
    fabric: str | None = None,
    sortBy: str | None = Query(None, alias="sortBy"),
    search: str | None = None,
    page: int = Query(1, ge=1),
    pageSize: int = Query(12, ge=1, le=100, alias="pageSize"),
):
    return await product_service.list_products(
        db,
        redis,
        category=category,
        min_price=minPrice,
        max_price=maxPrice,
        product_type=productType,
        material=material,
        leather_type=leatherType,
        sizes=sizes,
        colors=colors,
        fabric=fabric,
        sort_by=sortBy,
        search=search,
        page=page,
        page_size=pageSize,
    )


@router.get("/featured")
async def get_featured(db: DbSession, redis: RedisClient):
    return await product_service.get_featured(db, redis)


@router.get("/new-arrivals")
async def get_new_arrivals(db: DbSession, redis: RedisClient):
    return await product_service.get_new_arrivals(db, redis)


@router.get("/{slug}")
async def get_product(slug: str, db: DbSession, redis: RedisClient):
    return await product_service.get_by_slug(db, redis, slug)


@router.get("/{product_id}/related")
async def get_related_products(product_id: str, db: DbSession):
    return await product_service.get_related(db, product_id)
