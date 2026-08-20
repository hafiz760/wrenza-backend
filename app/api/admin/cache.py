from fastapi import APIRouter, HTTPException

from app.core.deps import AdminUser, RedisClient
from app.services import cache_service

router = APIRouter(prefix="/cache", tags=["Admin - Cache"])


@router.get("")
async def cache_summary(admin: AdminUser, redis: RedisClient):
    """Key counts per group, so the dashboard can show what is cached."""
    return {"groups": await cache_service.summary(redis)}


@router.delete("/{group}")
async def clear_cache(group: str, admin: AdminUser, redis: RedisClient):
    """Clear one cache group.

    Takes a group name rather than a pattern on purpose — see
    `cache_service` for what a free-form pattern could otherwise reach.
    """
    try:
        removed = await cache_service.clear(redis, group)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown cache group: {group}")
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"group": group, "cleared": removed}
