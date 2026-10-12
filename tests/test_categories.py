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
async def test_category_seo_fields_round_trip_through_admin_and_public_apis(
    client, admin_headers
):
    """SEO fields must be saved and visible to both dashboard and storefront.

    This prevents Swagger-only fields from being silently discarded on create,
    or hidden from the GET responses that the dashboard and storefront use.
    """
    body = {
        "name": "Leather Wallets",
        "slug": "leather-wallets",
        "description": "Genuine leather wallets for men in Pakistan.",
        "metaTitle": "Leather Wallets in Pakistan | Wrenza",
        "metaDescription": "Shop genuine leather wallets for men in Pakistan from Wrenza.",
        "canonicalUrl": "https://wrenza.com/products?category=leather-wallets",
        "isIndexable": True,
    }

    created = await client.post(
        "/api/v1/admin/categories", headers=admin_headers, json=body
    )
    assert created.status_code == 200, created.text
    category_id = created.json()["id"]

    for response in (created,):
        data = response.json()
        assert data["metaTitle"] == body["metaTitle"]
        assert data["metaDescription"] == body["metaDescription"]
        assert data["canonicalUrl"] == body["canonicalUrl"]
        assert data["isIndexable"] is True
        assert "updatedAt" in data

    admin_get = await client.get(
        f"/api/v1/admin/categories/{category_id}", headers=admin_headers
    )
    assert admin_get.status_code == 200, admin_get.text
    assert admin_get.json()["metaTitle"] == body["metaTitle"]

    public = await client.get("/api/v1/categories")
    assert public.status_code == 200, public.text
    category = next(item for item in public.json() if item["id"] == category_id)
    assert category["metaTitle"] == body["metaTitle"]
    assert category["metaDescription"] == body["metaDescription"]
    assert category["canonicalUrl"] == body["canonicalUrl"]
    assert category["isIndexable"] is True
    assert "updatedAt" in category


@pytest.mark.asyncio
async def test_category_seo_fields_update_through_put(client, admin_headers):
    """PUT must update SEO fields without requiring a slug or name change."""
    category_id = await _create_category(client, admin_headers, "Wallets")

    response = await client.put(
        f"/api/v1/admin/categories/{category_id}",
        headers=admin_headers,
        json={
            "metaTitle": "Updated Wallets | Wrenza",
            "metaDescription": "Updated category description.",
            "canonicalUrl": "https://wrenza.com/products?category=wallets",
            "isIndexable": False,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["metaTitle"] == "Updated Wallets | Wrenza"
    assert data["metaDescription"] == "Updated category description."
    assert data["canonicalUrl"] == "https://wrenza.com/products?category=wallets"
    assert data["isIndexable"] is False


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


async def _create_product_in(client, admin_headers, name, category_id):
    response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": name,
            "description": "A product.",
            "price": 1000,
            "stock": 5,
            "categoryId": category_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_product_count_is_products_not_child_categories(
    client, admin_headers
):
    """Regression: `productCount` used to be `len(children)` — a leaf
    category (no subcategories) always read 0 regardless of how many real
    products it held, and a parent's count was actually its subcategory
    count, not a product count at all."""
    card_holders = await _create_category(client, admin_headers, "Card Holders")
    await _create_product_in(client, admin_headers, "Slim Card Holder", card_holders)
    await _create_product_in(client, admin_headers, "Compact Card Holder", card_holders)

    response = await client.get("/api/v1/categories")
    tree = response.json()
    node = next(c for c in tree if c["id"] == card_holders)
    assert node["children"] == []
    assert node["productCount"] == 2


@pytest.mark.asyncio
async def test_product_count_rolls_up_through_children(client, admin_headers):
    """A parent with no products of its own (everything is filed under its
    children) still has to report a real total, not 0."""
    wallets = await _create_category(client, admin_headers, "Wallets")
    bifold = await _create_category(client, admin_headers, "Bifold", wallets)
    long = await _create_category(client, admin_headers, "Long", wallets)

    await _create_product_in(client, admin_headers, "Classic Bifold", bifold)
    await _create_product_in(client, admin_headers, "Slim Bifold", bifold)
    await _create_product_in(client, admin_headers, "Travel Long Wallet", long)

    response = await client.get("/api/v1/categories")
    tree = response.json()
    wallets_node = next(c for c in tree if c["id"] == wallets)
    bifold_node = next(c for c in wallets_node["children"] if c["id"] == bifold)
    long_node = next(c for c in wallets_node["children"] if c["id"] == long)

    assert bifold_node["productCount"] == 2
    assert long_node["productCount"] == 1
    assert wallets_node["productCount"] == 3


@pytest.mark.asyncio
async def test_filtering_by_parent_category_includes_child_products(
    client, admin_headers
):
    """Regression: `?category=<parent-slug>` used to match the category by
    exact slug only, so a parent with nothing filed directly under it (e.g.
    "Leather Wallets", whose products all live under "Bifold"/"Long")
    always returned zero results — the storefront's own category tile for
    it was a dead link."""
    wallets_response = await client.post(
        "/api/v1/admin/categories", headers=admin_headers, json={"name": "Wallets"}
    )
    wallets_id = wallets_response.json()["id"]
    wallets_slug = wallets_response.json()["slug"]
    bifold = await _create_category(client, admin_headers, "Bifold", wallets_id)

    await _create_product_in(client, admin_headers, "Classic Bifold", bifold)
    await _create_product_in(client, admin_headers, "Slim Bifold", bifold)

    response = await client.get(f"/api/v1/products?category={wallets_slug}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert {item["name"] for item in body["items"]} == {
        "Classic Bifold",
        "Slim Bifold",
    }


@pytest.mark.asyncio
async def test_filtering_by_unknown_category_returns_empty(client):
    response = await client.get("/api/v1/products?category=does-not-exist")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0
