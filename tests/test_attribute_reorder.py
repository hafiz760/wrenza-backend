"""Ordering for attributes and their terms.

Both carry a `position` column that nothing wrote to, so every row sat at 0 and
the list fell back to alphabetical. These cover the reorder endpoints.
"""

import pytest


async def _attribute(client, admin_headers, name):
    response = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _term(client, admin_headers, attribute_id, value):
    response = await client.post(
        f"/api/v1/admin/attributes/{attribute_id}/terms",
        headers=admin_headers,
        json={"value": value},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_reorder_terms_sets_positions_from_the_list(client, admin_headers):
    attribute = await _attribute(client, admin_headers, "Colour")
    black = await _term(client, admin_headers, attribute["id"], "Black")
    blue = await _term(client, admin_headers, attribute["id"], "Blue")
    green = await _term(client, admin_headers, attribute["id"], "Green")

    # Alphabetical until told otherwise
    listed = await client.get("/api/v1/admin/attributes", headers=admin_headers)
    current = next(a for a in listed.json() if a["id"] == attribute["id"])
    assert [t["value"] for t in current["terms"]] == ["Black", "Blue", "Green"]

    response = await client.patch(
        f"/api/v1/admin/attributes/{attribute['id']}/terms/reorder",
        headers=admin_headers,
        json={"ids": [green["id"], black["id"], blue["id"]]},
    )
    assert response.status_code == 200, response.text
    assert [t["value"] for t in response.json()] == ["Green", "Black", "Blue"]

    # Positions are contiguous, so repeated reordering cannot leave gaps
    assert [t["position"] for t in response.json()] == [0, 1, 2]

    listed = await client.get("/api/v1/admin/attributes", headers=admin_headers)
    current = next(a for a in listed.json() if a["id"] == attribute["id"])
    assert [t["value"] for t in current["terms"]] == ["Green", "Black", "Blue"]


@pytest.mark.asyncio
async def test_reorder_attributes(client, admin_headers):
    first = await _attribute(client, admin_headers, "Alpha")
    second = await _attribute(client, admin_headers, "Beta")

    response = await client.patch(
        "/api/v1/admin/attributes/reorder",
        headers=admin_headers,
        json={"ids": [second["id"], first["id"]]},
    )
    assert response.status_code == 200, response.text

    names = [a["name"] for a in response.json()]
    assert names.index("Beta") < names.index("Alpha")


@pytest.mark.asyncio
async def test_reorder_rejects_a_term_from_another_attribute(client, admin_headers):
    """A mismatched id means stale client data — better to fail than reorder
    something the admin was not looking at."""
    colour = await _attribute(client, admin_headers, "Colour")
    finish = await _attribute(client, admin_headers, "Finish")
    mine = await _term(client, admin_headers, colour["id"], "Black")
    theirs = await _term(client, admin_headers, finish["id"], "Brass")

    response = await client.patch(
        f"/api/v1/admin/attributes/{colour['id']}/terms/reorder",
        headers=admin_headers,
        json={"ids": [mine["id"], theirs["id"]]},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reorder_requires_admin(client, auth_headers):
    response = await client.patch(
        "/api/v1/admin/attributes/reorder",
        headers=auth_headers,
        json={"ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 403
