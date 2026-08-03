from sqlalchemy import select, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.product import Product
from app.schemas.common import PaginatedResponse
from app.schemas.product import ProductListOut
from app.services.product_service import _product_to_list_out
from app.utils.pagination import paginate


async def search_products(
    db: AsyncSession,
    query: str,
    page: int = 1,
    page_size: int = 12,
) -> PaginatedResponse[ProductListOut]:
    """Full-text search using PostgreSQL ts_vector."""
    search_query = (
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.category))
        .where(
            Product.is_active.is_(True),
            func.to_tsvector("english", Product.name + " " + Product.description).match(
                func.plainto_tsquery("english", query)
            ),
        )
        .order_by(desc(Product.rating))
    )

    result = await paginate(search_query, page, page_size, db)
    items = [_product_to_list_out(p) for p in result["items"]]

    return PaginatedResponse(
        items=items,
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )
