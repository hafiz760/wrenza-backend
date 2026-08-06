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
async def test_deactivate_via_put_replaces_soft_delete(client, admin_headers):
    """PUT with isActive:false is the supported way to hide a category."""
    cat_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.put(
        f"/api/v1/admin/categories/{cat_id}",
        headers=admin_headers,
        json={"isActive": False},
    )
    assert response.status_code == 200
    assert response.json()["isActive"] is False

    # Row survives, and the public tree hides it
    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    assert any(c["id"] == cat_id for c in listed.json())

    public = await client.get("/api/v1/categories")
    assert [c for c in public.json() if c["id"] == cat_id] == []


@pytest.mark.asyncio
async def test_permanent_delete_removes_unused_category(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.delete(
        f"/api/v1/admin/categories/{cat_id}", headers=admin_headers
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
        f"/api/v1/admin/categories/{cat_id}", headers=admin_headers
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
        f"/api/v1/admin/categories/{parent_id}", headers=admin_headers
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
        f"/api/v1/admin/categories/{cat_id}?force=true",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["productsUncategorized"] == 1

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
        f"/api/v1/admin/categories/{parent_id}?force=true",
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["subcategoriesPromoted"] == 1

    listed = await client.get("/api/v1/admin/categories", headers=admin_headers)
    child = next(c for c in listed.json() if c["id"] == child_id)
    assert child["parentId"] is None


@pytest.mark.asyncio
async def test_permanent_delete_missing_returns_404(client, admin_headers):
    response = await client.delete(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_permanent_delete_requires_admin(client, auth_headers):
    response = await client.delete(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_category_by_id(client, admin_headers):
    cat_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.get(
        f"/api/v1/admin/categories/{cat_id}", headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == cat_id
    assert data["name"] == "Wallets"
    assert data["slug"] == "wallets"
    assert data["isActive"] is True


@pytest.mark.asyncio
async def test_get_category_missing_returns_404(client, admin_headers):
    response = await client.get(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_category_malformed_id_returns_404_not_500(client, admin_headers):
    response = await client.get(
        "/api/v1/admin/categories/not-a-uuid", headers=admin_headers
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_category_requires_admin(client, auth_headers):
    response = await client.get(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_public_tree_nests_beyond_two_levels(client, admin_headers):
    """The tree is built from parent_id, so depth is not capped by eager loading."""
    wallets = await _create_category(client, admin_headers, "Wallets")
    bifold = await _create_category(client, admin_headers, "Bifold", wallets)
    await _create_category(client, admin_headers, "Slim Bifold", bifold)

    response = await client.get("/api/v1/categories")
    assert response.status_code == 200, response.text

    tree = response.json()
    root = next(c for c in tree if c["id"] == wallets)
    child = next(c for c in root["children"] if c["id"] == bifold)
    assert [g["name"] for g in child["children"]] == ["Slim Bifold"]


@pytest.mark.asyncio
async def test_inactive_category_drops_its_whole_subtree(client, admin_headers):
    """Deactivating a parent hides its descendants too — they are unreachable."""
    wallets = await _create_category(client, admin_headers, "Wallets")
    bifold = await _create_category(client, admin_headers, "Bifold", wallets)
    await _create_category(client, admin_headers, "Slim Bifold", bifold)

    await client.put(
        f"/api/v1/admin/categories/{bifold}",
        headers=admin_headers,
        json={"isActive": False},
    )

    response = await client.get("/api/v1/categories")
    tree = response.json()

    def flatten(nodes):
        for node in nodes:
            yield node["name"]
            yield from flatten(node["children"])

    names = list(flatten(tree))
    assert "Wallets" in names
    # The deactivated node goes, and the still-active grandchild goes with it
    assert "Bifold" not in names
    assert "Slim Bifold" not in names
