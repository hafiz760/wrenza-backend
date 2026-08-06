from fastapi import APIRouter, Query

from app.core.deps import DbSession, RedisClient
from app.schemas.filters import ProductFiltersOut
from app.schemas.review import ProductReviewsOut
from app.services import product_service, review_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("")
async def list_products(
    db: DbSession,
    redis: RedisClient,
    category: str | None = None,
    minPrice: float | None = Query(None, alias="minPrice"),
    maxPrice: float | None = Query(None, alias="maxPrice"),
    productType: str | None = Query(None, alias="productType"),
    attrs: list[str] | None = Query(
        None,
        description=(
            "Attribute term slugs to filter by, repeatable. "
            "e.g. ?attrs=black&attrs=silver — a product must offer all of them."
        ),
    ),
    ids: list[str] | None = Query(
        None, description="Return only these product ids, repeatable."
    ),
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
        attribute_terms=attrs,
        ids=ids,
        sort_by=sortBy,
        search=search,
        page=page,
        page_size=pageSize,
    )


@router.get("/filters", response_model=ProductFiltersOut)
async def get_filters(db: DbSession):
    """Available filter facets and price bounds for the catalog sidebar."""
    return await product_service.get_filters(db)


@router.get("/featured")
async def get_featured(db: DbSession, redis: RedisClient):
    return await product_service.get_featured(db, redis)


@router.get("/new-arrivals")
async def get_new_arrivals(db: DbSession, redis: RedisClient):
    return await product_service.get_new_arrivals(db, redis)


# Declared before "/{slug}" so the literal segment is not captured as a slug
@router.get("/{slug}/reviews", response_model=ProductReviewsOut)
async def get_product_reviews(
    slug: str,
    db: DbSession,
    page: int = Query(1, ge=1),
    pageSize: int = Query(10, ge=1, le=50, alias="pageSize"),
):
    """Approved reviews for a product, with the rating histogram."""
    return await review_service.list_public_reviews(db, slug, page, pageSize)


@router.get("/{slug}")
async def get_product(slug: str, db: DbSession, redis: RedisClient):
    return await product_service.get_by_slug(db, redis, slug)


@router.get("/{product_id}/related")
async def get_related_products(product_id: str, db: DbSession):
    return await product_service.get_related(db, product_id)
