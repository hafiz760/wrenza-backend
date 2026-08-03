import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def generate_slug(text: str) -> str:
    """Generate a URL-friendly slug from text."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


async def ensure_unique_slug(
    db: AsyncSession,
    model,
    slug: str,
    exclude_id: uuid.UUID | None = None,
) -> str:
    """Ensure slug is unique, appending a suffix if needed."""
    base_slug = slug
    counter = 1

    while True:
        query = select(model.id).where(model.slug == slug)
        if exclude_id:
            query = query.where(model.id != exclude_id)
        result = await db.scalar(query)
        if result is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


async def ensure_unique_slug_scoped(
    db: AsyncSession,
    model,
    slug: str,
    scope_field: str,
    scope_value,
    exclude_id: uuid.UUID | None = None,
) -> str:
    """Ensure slug is unique within a scope (e.g. terms within one attribute)."""
    base_slug = slug
    counter = 1

    while True:
        query = select(model.id).where(
            model.slug == slug,
            getattr(model, scope_field) == scope_value,
        )
        if exclude_id:
            query = query.where(model.id != exclude_id)
        result = await db.scalar(query)
        if result is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1
