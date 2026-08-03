from math import ceil

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import PaginatedResponse


async def paginate(
    query,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> dict:
    """Apply offset-based pagination matching frontend's page/pageSize pattern."""
    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply offset/limit
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    items = list(result.scalars().all())

    total_pages = ceil(total / page_size) if page_size > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }
