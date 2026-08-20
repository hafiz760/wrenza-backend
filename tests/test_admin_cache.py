"""The dashboard's cache view, and what it refuses to clear.

The Redis this talks to is shared with other applications on the same host, and
the `wz:` namespace holds more than caches. Three groups inside it are not safe
to clear from a button, so the endpoint takes a group name rather than a
pattern and refuses the protected ones.
"""

import pytest

from tests.conftest import mock_redis


@pytest.mark.asyncio
async def test_summary_counts_cached_keys(client, admin_headers):
    mock_redis.store["wz:products:detail:a"] = "{}"
    mock_redis.store["wz:products:detail:b"] = "{}"
    mock_redis.store["wz:categories:tree"] = "{}"

    response = await client.get("/api/v1/admin/cache", headers=admin_headers)
    assert response.status_code == 200, response.text

    groups = {g["key"]: g for g in response.json()["groups"]}
    assert groups["products"]["count"] == 2
    assert groups["categories"]["count"] == 1


@pytest.mark.asyncio
async def test_clearing_products_removes_only_that_group(client, admin_headers):
    mock_redis.store["wz:products:detail:a"] = "{}"
    mock_redis.store["wz:categories:tree"] = "{}"

    response = await client.delete(
        "/api/v1/admin/cache/products", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["cleared"] == 1

    assert "wz:products:detail:a" not in mock_redis.store
    assert "wz:categories:tree" in mock_redis.store


@pytest.mark.parametrize("group", ["denylist", "ratelimit", "queue"])
@pytest.mark.asyncio
async def test_protected_groups_cannot_be_cleared(client, admin_headers, group):
    """Clearing the denylist would un-revoke tokens; clearing the queue would
    discard emails that have been accepted but not sent."""
    mock_redis.store["wz:denylist:abc"] = "1"
    mock_redis.store["wz:queue"] = "1"
    mock_redis.store["wz:ratelimit:1.2.3.4"] = "1"

    response = await client.delete(
        f"/api/v1/admin/cache/{group}", headers=admin_headers
    )
    assert response.status_code == 400, response.text

    assert mock_redis.store["wz:denylist:abc"] == "1"
    assert mock_redis.store["wz:queue"] == "1"


@pytest.mark.asyncio
async def test_unknown_group_is_404(client, admin_headers):
    response = await client.delete(
        "/api/v1/admin/cache/nonsense", headers=admin_headers
    )
    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_clearing_never_touches_another_application(client, admin_headers):
    """The namespace exists because this Redis is shared."""
    mock_redis.store["otherapp:products:detail:a"] = "{}"
    mock_redis.store["wz:products:detail:a"] = "{}"

    await client.delete("/api/v1/admin/cache/products", headers=admin_headers)
    assert "otherapp:products:detail:a" in mock_redis.store


@pytest.mark.asyncio
async def test_cache_view_requires_admin(client, auth_headers):
    response = await client.get("/api/v1/admin/cache", headers=auth_headers)
    assert response.status_code in (401, 403), response.text
