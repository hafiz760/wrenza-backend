"""Cache inspection and clearing for the dashboard.

Deliberately group-based rather than pattern-based. A raw pattern from the
client could reach keys that share the namespace but are not caches at all,
and clearing those is destructive in ways that are not obvious:

  wz:denylist:*   revoked tokens — clearing makes logged-out and compromised
                  sessions valid again until they expire
  wz:queue*       arq's job queue — clearing discards emails that have been
                  accepted but not yet sent
  wz:ratelimit:*  abuse counters — clearing hands every caller a fresh budget

Those are listed so they can be seen, and refused so they cannot be cleared.
"""

from dataclasses import dataclass

from redis.asyncio import Redis

from app.utils.cache import CACHE_PREFIX, cache_delete_pattern


@dataclass(frozen=True)
class CacheGroup:
    key: str
    label: str
    pattern: str
    clearable: bool
    note: str = ""


GROUPS: tuple[CacheGroup, ...] = (
    CacheGroup(
        "products",
        "Products",
        "products:*",
        True,
        "Detail, listings, featured and new arrivals.",
    ),
    CacheGroup("categories", "Categories", "categories:*", True, "The category tree."),
    CacheGroup(
        "denylist",
        "Revoked tokens",
        "denylist:*",
        False,
        "Clearing would make logged-out sessions valid again.",
    ),
    CacheGroup(
        "ratelimit",
        "Rate limits",
        "ratelimit:*",
        False,
        "Clearing resets every abuse counter.",
    ),
    CacheGroup(
        "queue",
        "Job queue",
        "queue*",
        False,
        "Holds queued emails that have not been sent yet.",
    ),
)

BY_KEY = {g.key: g for g in GROUPS}


async def _count(redis: Redis, pattern: str) -> int:
    """Count matching keys with SCAN.

    Never KEYS: it blocks the server for the whole scan, and this Redis is
    shared with other applications on the same host.
    """
    full = f"{CACHE_PREFIX}:{pattern}"
    cursor, total = 0, 0
    while True:
        cursor, keys = await redis.scan(cursor, match=full, count=250)
        total += len(keys)
        if cursor == 0:
            return total


async def summary(redis: Redis) -> list[dict]:
    return [
        {
            "key": g.key,
            "label": g.label,
            "pattern": f"{CACHE_PREFIX}:{g.pattern}",
            "clearable": g.clearable,
            "note": g.note,
            "count": await _count(redis, g.pattern),
        }
        for g in GROUPS
    ]


async def clear(redis: Redis, group_key: str) -> int:
    """Clear one group. Returns how many keys were removed.

    Raises KeyError for an unknown group and PermissionError for a protected
    one, so the router can map each to the right status code.
    """
    group = BY_KEY.get(group_key)
    if group is None:
        raise KeyError(group_key)
    if not group.clearable:
        raise PermissionError(group.note)

    removed = await _count(redis, group.pattern)
    await cache_delete_pattern(redis, group.pattern)
    return removed
