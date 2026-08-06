import pytest


async def _make_category(client, admin_headers, name):
    response = await client.post(
        "/api/v1/admin/categories", headers=admin_headers, json={"name": name}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_returns_only_id_and_name(client, admin_headers):
    await _make_category(client, admin_headers, "Wallets")

    response = await client.get(
        "/api/v1/admin/options/categories", headers=admin_headers
    )
    assert response.status_code == 200
    row = response.json()[0]
    assert set(row.keys()) == {"id", "name"}
    assert row["name"] == "Wallets"


@pytest.mark.asyncio
async def test_unknown_resource_is_404_and_lists_allowed(client, admin_headers):
    response = await client.get("/api/v1/admin/options/users", headers=admin_headers)
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "Unknown resource 'users'" in detail
    assert "categories" in detail


@pytest.mark.asyncio
async def test_limit_caps_large_result_sets(client, admin_headers):
    for i in range(30):
        await _make_category(client, admin_headers, f"Cat {i:03d}")

    default = await client.get(
        "/api/v1/admin/options/categories", headers=admin_headers
    )
    assert len(default.json()) == 20  # default limit, not all 30

    capped = await client.get(
        "/api/v1/admin/options/categories?limit=5", headers=admin_headers
    )
    assert len(capped.json()) == 5


@pytest.mark.asyncio
async def test_limit_is_bounded(client, admin_headers):
    too_big = await client.get(
        "/api/v1/admin/options/categories?limit=5000", headers=admin_headers
    )
    assert too_big.status_code == 422  # le=100 rejects it


@pytest.mark.asyncio
async def test_search_narrows_results(client, admin_headers):
    await _make_category(client, admin_headers, "Leather Wallets")
    await _make_category(client, admin_headers, "Canvas Bags")

    response = await client.get(
        "/api/v1/admin/options/categories?search=wall", headers=admin_headers
    )
    names = [r["name"] for r in response.json()]
    assert names == ["Leather Wallets"]


@pytest.mark.asyncio
async def test_ids_resolves_selection_outside_the_first_page(client, admin_headers):
    """The classic dropdown bug: a selected value past the limit must still resolve."""
    for i in range(25):
        await _make_category(client, admin_headers, f"Cat {i:03d}")
    last_id = await _make_category(client, admin_headers, "Zzz Last")

    listed = await client.get(
        "/api/v1/admin/options/categories", headers=admin_headers
    )
    assert last_id not in [r["id"] for r in listed.json()]  # beyond the page

    resolved = await client.get(
        f"/api/v1/admin/options/categories?ids={last_id}", headers=admin_headers
    )
    assert [r["name"] for r in resolved.json()] == ["Zzz Last"]


@pytest.mark.asyncio
async def test_ids_resolves_even_when_deactivated(client, admin_headers):
    """A deactivated but still-selected row must render its name, not a blank."""
    cat_id = await _make_category(client, admin_headers, "Retired")
    await client.put(
        f"/api/v1/admin/categories/{cat_id}",
        headers=admin_headers,
        json={"isActive": False},
    )

    listed = await client.get(
        "/api/v1/admin/options/categories", headers=admin_headers
    )
    assert cat_id not in [r["id"] for r in listed.json()]

    resolved = await client.get(
        f"/api/v1/admin/options/categories?ids={cat_id}", headers=admin_headers
    )
    assert [r["name"] for r in resolved.json()] == ["Retired"]


@pytest.mark.asyncio
async def test_exclude_prevents_self_parenting(client, admin_headers):
    cat_id = await _make_category(client, admin_headers, "Wallets")

    response = await client.get(
        f"/api/v1/admin/options/categories?exclude={cat_id}", headers=admin_headers
    )
    assert cat_id not in [r["id"] for r in response.json()]


@pytest.mark.asyncio
async def test_malformed_id_does_not_500(client, admin_headers):
    response = await client.get(
        "/api/v1/admin/options/categories?ids=not-a-uuid&exclude=also-junk",
        headers=admin_headers,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_inactive_rows_excluded_from_normal_listing(client, admin_headers):
    cat_id = await _make_category(client, admin_headers, "Hidden")
    await client.put(
        f"/api/v1/admin/categories/{cat_id}",
        headers=admin_headers,
        json={"isActive": False},
    )

    response = await client.get(
        "/api/v1/admin/options/categories", headers=admin_headers
    )
    assert cat_id not in [r["id"] for r in response.json()]


@pytest.mark.asyncio
async def test_options_requires_admin(client, auth_headers):
    response = await client.get(
        "/api/v1/admin/options/categories", headers=auth_headers
    )
    assert response.status_code == 403


async def _make_attribute_with_terms(client, admin_headers, name, values):
    created = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": name}
    )
    attr_id = created.json()["id"]
    for value in values:
        await client.post(
            f"/api/v1/admin/attributes/{attr_id}/terms",
            headers=admin_headers,
            json={"value": value},
        )
    return attr_id


@pytest.mark.asyncio
async def test_attribute_terms_scoped_to_parent(client, admin_headers):
    colour = await _make_attribute_with_terms(
        client, admin_headers, "Colour", ["Black", "Tan"]
    )
    await _make_attribute_with_terms(client, admin_headers, "Hardware", ["Silver"])

    response = await client.get(
        f"/api/v1/admin/options/attribute-terms?parent={colour}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert sorted(r["name"] for r in response.json()) == ["Black", "Tan"]


@pytest.mark.asyncio
async def test_attribute_terms_require_parent(client, admin_headers):
    await _make_attribute_with_terms(client, admin_headers, "Colour", ["Black"])

    response = await client.get(
        "/api/v1/admin/options/attribute-terms", headers=admin_headers
    )
    assert response.status_code == 422
    assert "requires a valid `parent` id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_attribute_terms_search_within_parent(client, admin_headers):
    colour = await _make_attribute_with_terms(
        client, admin_headers, "Colour", ["Black", "Tan", "Cognac"]
    )
    response = await client.get(
        f"/api/v1/admin/options/attribute-terms?parent={colour}&search=ta",
        headers=admin_headers,
    )
    assert [r["name"] for r in response.json()] == ["Tan"]
