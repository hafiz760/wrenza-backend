"""Instagram Graph API integration.

Mirrors the wrenzaleather Instagram Business account's own media onto the
storefront homepage. Read-only, and deliberately narrow: no posting, no
comments, no messages — just enough to list recent posts/reels.

The access token lives in `StoreSettings`, not `.env` — see the model for
why. `refresh_token` exchanges it for a fresh 60-day token; the worker cron
calls it weekly, well inside Instagram's minimum 24h-old requirement.
"""

from datetime import datetime, timezone

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services import settings_service
from app.utils.cache import cache_get, cache_key, cache_set

logger = structlog.get_logger()

GRAPH_BASE = "https://graph.instagram.com/v23.0"
MEDIA_FIELDS = "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp"
MEDIA_LIMIT = 12
CACHE_TTL = 1800  # 30 min


async def _fetch_media(business_id: str, access_token: str) -> list[dict]:
    """The actual Graph API call — split out so tests can monkeypatch it
    instead of mocking httpx internals, matching `safepay_service`'s pattern."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{GRAPH_BASE}/{business_id}/media",
            params={
                "fields": MEDIA_FIELDS,
                "limit": MEDIA_LIMIT,
                "access_token": access_token,
            },
        )
        response.raise_for_status()
    return response.json().get("data", [])


async def get_media(db: AsyncSession, redis: Redis) -> list[dict]:
    """Cached, trimmed media list — or [] if unconfigured or on any failure.

    Fails open: a missing token or an Instagram outage must never break the
    homepage, same reasoning as `Settings.email_enabled` elsewhere.
    """
    business_id = get_settings().INSTAGRAM_BUSINESS_ID
    store_settings = await settings_service.get_or_create(db)
    if not store_settings.instagram_access_token or not business_id:
        return []

    ck = cache_key("instagram", "media")
    cached = await cache_get(redis, ck)
    if cached is not None:
        return cached

    try:
        raw_items = await _fetch_media(
            business_id, store_settings.instagram_access_token
        )
    except httpx.HTTPError as exc:
        logger.warning("instagram_media_fetch_failed", error=str(exc))
        return []

    items = []
    for item in raw_items:
        # A VIDEO's own media_url is the raw playable .mp4 — no good as an
        # <img> src for a static grid tile, so a reel needs its
        # thumbnail_url specifically and is dropped without one, rather than
        # rendering a broken image. Every other type only ever has media_url.
        if item.get("media_type") == "VIDEO":
            image_url = item.get("thumbnail_url")
        else:
            image_url = item.get("media_url")
        if not image_url:
            continue

        items.append(
            {
                "id": item["id"],
                "mediaType": item.get("media_type"),
                "mediaUrl": image_url,
                "permalink": item.get("permalink"),
                "caption": (item.get("caption") or "").split("\n")[0][:200],
                "timestamp": item.get("timestamp"),
            }
        )

    await cache_set(redis, ck, items, ttl=CACHE_TTL)
    return items


async def _call_refresh_endpoint(access_token: str) -> str:
    """Split out so tests can monkeypatch it instead of mocking httpx."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
        )
        response.raise_for_status()
    return response.json()["access_token"]


async def refresh_token(db: AsyncSession) -> bool:
    """Exchanges the stored token for a fresh 60-day one.

    Leaves the stored token untouched on any failure — a transient outage
    must not wipe out a token that still has weeks left on it.
    """
    store_settings = await settings_service.get_or_create(db)
    if not store_settings.instagram_access_token:
        return False

    try:
        new_token = await _call_refresh_endpoint(store_settings.instagram_access_token)
    except (httpx.HTTPError, KeyError) as exc:
        logger.error("instagram_token_refresh_failed", error=str(exc))
        return False

    store_settings.instagram_access_token = new_token
    store_settings.instagram_token_refreshed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("instagram_token_refreshed")
    return True
