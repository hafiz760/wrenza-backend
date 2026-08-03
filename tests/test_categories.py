import pytest


async def _create_category(client, admin_headers, name, parent_id=None):
    body = {"name": name}
    if parent_id:
        body["parentId"] = parent_id
    response = await client.post(
        "/api/v1/admin/categories", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_soft_delete_keeps_the_row(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.delete(
        f"/api/v1/admin/categories/{cat_id}", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Category deactivated"

    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    row = next(c for c in listed.json() if c["id"] == cat_id)
    assert row["is_active"] is False


@pytest.mark.asyncio
async def test_permanent_delete_removes_unused_category(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.delete(
        f"/api/v1/admin/categories/{cat_id}/permanent", headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Category permanently deleted"

    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    assert [c for c in listed.json() if c["id"] == cat_id] == []


@pytest.mark.asyncio
async def test_permanent_delete_blocked_by_products(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")
    await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Bifold",
            "description": "A leather bifold wallet.",
            "price": 4500,
            "categoryId": cat_id,
            "stock": 5,
        },
    )

    response = await client.delete(
        f"/api/v1/admin/categories/{cat_id}/permanent", headers=admin_headers
    )
    assert response.status_code == 409
    assert "1 product(s)" in response.json()["detail"]

    # Still there
    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    assert any(c["id"] == cat_id for c in listed.json())


@pytest.mark.asyncio
async def test_permanent_delete_blocked_by_subcategory(client, admin_headers):
    parent_id = await _create_category(client, admin_headers, "Wallets")
    await _create_category(client, admin_headers, "Bifold", parent_id=parent_id)

    response = await client.delete(
        f"/api/v1/admin/categories/{parent_id}/permanent", headers=admin_headers
    )
    assert response.status_code == 409
    assert "1 subcategory(ies)" in response.json()["detail"]


@pytest.mark.asyncio
async def test_force_delete_uncategorizes_products(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")
    created = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Bifold",
            "description": "A leather bifold wallet.",
            "price": 4500,
            "categoryId": cat_id,
            "stock": 5,
        },
    )
    slug = created.json()["slug"]

    response = await client.delete(
        f"/api/v1/admin/categories/{cat_id}/permanent?force=true",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["products_uncategorized"] == 1

    # The product survives, but is now uncategorized
    product = await client.get(f"/api/v1/products/{slug}")
    assert product.status_code == 200
    assert product.json()["category"] is None


@pytest.mark.asyncio
async def test_force_delete_promotes_subcategories(client, admin_headers):
    parent_id = await _create_category(client, admin_headers, "Wallets")
    child_id = await _create_category(
        client, admin_headers, "Bifold", parent_id=parent_id
    )

    response = await client.delete(
        f"/api/v1/admin/categories/{parent_id}/permanent?force=true",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["subcategories_promoted"] == 1

    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    child = next(c for c in listed.json() if c["id"] == child_id)
    assert child["parent_id"] is None


@pytest.mark.asyncio
async def test_permanent_delete_missing_returns_404(client, admin_headers):
    response = await client.delete(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000/permanent",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_permanent_delete_requires_admin(client, auth_headers):
    response = await client.delete(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000/permanent",
        headers=auth_headers,
    )
    assert response.status_code == 403
