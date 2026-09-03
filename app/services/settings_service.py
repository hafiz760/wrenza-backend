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
    if settings is None:
        settings = StoreSettings()
        # One-time seed from .env — after this the DB row is authoritative,
        # since the refresh job overwrites it with tokens .env never sees.
        env = get_settings()
        if env.INSTAGRAM_ACCESS_TOKEN:
            settings.instagram_access_token = env.INSTAGRAM_ACCESS_TOKEN
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings
