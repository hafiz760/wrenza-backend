"""Admin visibility and status for collections.

The admin listing reused the storefront's query, which filters out inactive
collections. Deactivating one therefore removed it from the only screen that
could reactivate it. The same query also omitted `isActive` entirely, so the
dashboard read the missing field as falsy and labelled every collection
"Inactive" — including active ones.

Same shape of bug as `test_product_trash.py`; these stop it recurring here.
"""

import pytest


async def _collection(client, admin_headers, name="Autumn Edit", **extra):
    body = {"name": name, "image": "https://cdn.example/a.webp"}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/collections", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _set_active(client, admin_headers, collection_id, active):
    response = await client.put(
        f"/api/v1/admin/collections/{collection_id}",
        headers=admin_headers,
        json={"isActive": active},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _slugs(payload) -> set[str]:
    return {item["slug"] for item in payload}


# ── Visibility ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_sees_inactive_collections(client, admin_headers):
    """The bug: deactivating a collection made it unreachable forever."""
    collection = await _collection(client, admin_headers, name="Hidden Edit")
    await _set_active(client, admin_headers, collection["id"], False)

    response = await client.get("/api/v1/admin/collections", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert "hidden-edit" in _slugs(response.json())


@pytest.mark.asyncio
async def test_storefront_hides_inactive_collections(client, admin_headers):
    """The admin fix must not leak inactive collections to shoppers."""
    collection = await _collection(client, admin_headers, name="Retired Edit")
    await _set_active(client, admin_headers, collection["id"], False)

    response = await client.get("/api/v1/collections")
    assert response.status_code == 200, response.text
    assert "retired-edit" not in _slugs(response.json())


@pytest.mark.asyncio
async def test_deactivated_collection_can_be_reactivated(client, admin_headers):
    """The round trip the original bug made impossible."""
    collection = await _collection(client, admin_headers, name="Comeback Edit")
    await _set_active(client, admin_headers, collection["id"], False)
    restored = await _set_active(client, admin_headers, collection["id"], True)

    assert restored["isActive"] is True
    response = await client.get("/api/v1/collections")
    assert "comeback-edit" in _slugs(response.json())


# ── The isActive field itself ───────────────────────────────────


@pytest.mark.asyncio
async def test_admin_list_reports_active_status(client, admin_headers):
    """The dashboard renders status from this field; missing read as false."""
    await _collection(client, admin_headers, name="Live Edit")

    response = await client.get("/api/v1/admin/collections", headers=admin_headers)
    row = next(c for c in response.json() if c["slug"] == "live-edit")
    assert row["isActive"] is True


@pytest.mark.asyncio
async def test_create_and_update_return_active_status(client, admin_headers):
    """Without this the panel flips to "Inactive" right after a save."""
    created = await _collection(client, admin_headers, name="Fresh Edit")
    assert created["isActive"] is True

    updated = await client.put(
        f"/api/v1/admin/collections/{created['id']}",
        headers=admin_headers,
        json={"tagline": "Cut and stitched by hand"},
    )
    assert updated.json()["isActive"] is True


@pytest.mark.asyncio
async def test_public_payload_omits_active_status(client, admin_headers):
    """Every public collection is active, so the flag carries no information."""
    await _collection(client, admin_headers, name="Public Edit")

    response = await client.get("/api/v1/collections")
    row = next(c for c in response.json() if c["slug"] == "public-edit")
    assert "isActive" not in row
