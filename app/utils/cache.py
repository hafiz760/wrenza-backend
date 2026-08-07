import json
from typing import Any

from redis.asyncio import Redis

# Namespaces every key, so this Redis can be shared with other apps
CACHE_PREFIX = "wz"
DEFAULT_TTL = 300  # 5 minutes
TTL_SHORT = 300    # 5 min — product lists (filtered, paginated)
TTL_MEDIUM = 1800  # 30 min — featured, new arrivals, categories
TTL_LONG = 7200    # 2 hours — product detail (rarely changes)


def cache_key(*parts: str) -> str:
    """Build a namespaced cache key: wz:products:list:page1."""
    return f"{CACHE_PREFIX}:{':'.join(parts)}"


async def cache_get(redis: Redis, key: str) -> Any | None:
    """Get a cached value, returning deserialized JSON or None."""
    data = await redis.get(key)
    if data:
        return json.loads(data)
    return None


async def cache_set(redis: Redis, key: str, data: Any, ttl: int = DEFAULT_TTL) -> None:
    """Cache a value as JSON with a TTL."""
    await redis.set(key, json.dumps(data, default=str), ex=ttl)


async def cache_delete_pattern(redis: Redis, pattern: str) -> None:
    """Delete all keys matching a pattern (e.g., wz:products:*)."""
    full_pattern = f"{CACHE_PREFIX}:{pattern}"
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor, match=full_pattern, count=100)
        if keys:
            await redis.delete(*keys)
        if cursor == 0:
            break
