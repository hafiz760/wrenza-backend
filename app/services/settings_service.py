from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.settings import StoreSettings


async def get_or_create(db: AsyncSession) -> StoreSettings:
    """Settings are a single row, created lazily on first access.

    Shared by the admin router, the public settings endpoint, and order
    calculation — all three need the same row, and only one of them should
    own the "create it if missing" logic.
    """
    settings = await db.scalar(select(StoreSettings).limit(1))
    is_new = settings is None
    if is_new:
        settings = StoreSettings()
        db.add(settings)

    # Seed from .env whenever the column is still empty — not just on a
    # brand-new row. A store that already had a settings row (tax rate,
    # shipping cost, ...) before INSTAGRAM_ACCESS_TOKEN existed would
    # otherwise never pick it up, since the row is never "created" again.
    # After this first backfill the DB row is authoritative — the refresh
    # job overwrites it with tokens .env never sees.
    env = get_settings()
    needs_seed = not settings.instagram_access_token and env.INSTAGRAM_ACCESS_TOKEN
    if needs_seed:
        settings.instagram_access_token = env.INSTAGRAM_ACCESS_TOKEN

    if is_new or needs_seed:
        await db.commit()
        await db.refresh(settings)
    return settings
