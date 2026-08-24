import pytest
import pytest_asyncio

ADDRESS = {
    "email": "buyer@example.com",
    "phone": "03001234567",
    "firstName": "Buyer",
    "lastName": "One",
    "street": "1 Test St",
    "city": "Lahore",
    "state": "Punjab",
    "postalCode": "54000",
}


async def _simple_product(client, admin_headers, stock=10, price=1000):
    r = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Plain Belt", "description": "A belt.", "price": price, "stock": stock},
    )
    return r.json()["id"]


@pytest_asyncio.fixture
async def variable_product(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Bifold", "description": "Wallet.", "kind": "variable", "price": 4500},
    )
    pid = product.json()["id"]

    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Colour"}
    )
    aid = attr.json()["id"]
    terms = []
    for value in ("Black", "Tan"):
        t = await client.post(
            f"/api/v1/admin/attributes/{aid}/terms",
            headers=admin_headers,
            json={"value": value},
        )
        terms.append(t.json()["id"])

    await client.put(
        f"/api/v1/admin/products/{pid}/attributes",
        headers=admin_headers,
        json={"attributes": [{"attributeId": aid, "termIds": terms}]},
    )
    generated = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    variations = generated.json()

    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={"variations": [{"id": v["id"], "stock": 5, "price": 4500} for v in variations]},
    )
    return {"product_id": pid, "variations": variations}


@pytest.mark.asyncio
async def test_variable_product_requires_variation_id(client, variable_product):
    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": variable_product["product_id"], "quantity": 1}]},
    )
    assert response.status_code == 422
    assert "variationId is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_simple_product_rejects_variation_id(client, admin_headers, variable_product):
    pid = await _simple_product(client, admin_headers)
    response = await client.post(
        "/api/v1/checkout",
        json={
            **ADDRESS,
            "items": [
                {
                    "productId": pid,
                    "quantity": 1,
                    "variationId": variable_product["variations"][0]["id"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "do not send variationId" in response.json()["detail"]


@pytest.mark.asyncio
async def test_variation_from_another_product_rejected(
    client, admin_headers, variable_product
):
    other = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Other", "description": "x", "kind": "variable", "price": 100},
    )
    response = await client.post(
        "/api/v1/checkout",
        json={
            **ADDRESS,
            "items": [
                {
                    "productId": other.json()["id"],
                    "quantity": 1,
                    "variationId": variable_product["variations"][0]["id"],
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "does not belong" in response.json()["detail"]


@pytest.mark.asyncio
async def test_inactive_variation_rejected(client, admin_headers, variable_product):
    pid = variable_product["product_id"]
    var = variable_product["variations"][0]
    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={"variations": [{"id": var["id"], "isActive": False}]},
    )

    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1, "variationId": var["id"]}]},
    )
    assert response.status_code == 422
    assert "unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_checkout_deducts_variation_stock_not_product(
    client, admin_headers, variable_product
):
    pid = variable_product["product_id"]
    var = variable_product["variations"][0]

    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 2, "variationId": var["id"]}]},
    )
    assert response.status_code == 200

    listed = await client.get(
        f"/api/v1/admin/products/{pid}/variations", headers=admin_headers
    )
    updated = next(v for v in listed.json() if v["id"] == var["id"])
    assert updated["stock"] == 3  # 5 - 2


@pytest.mark.asyncio
async def test_insufficient_variation_stock(client, variable_product):
    pid = variable_product["product_id"]
    var = variable_product["variations"][0]
    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 99, "variationId": var["id"]}]},
    )
    assert response.status_code == 400
    assert "Insufficient stock" in response.json()["detail"]


@pytest.mark.asyncio
async def test_order_snapshot_records_chosen_attributes(client, variable_product):
    pid = variable_product["product_id"]
    var = variable_product["variations"][0]

    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 1, "variationId": var["id"]}]},
    )
    item = response.json()["items"][0]
    assert "variation" in item["product"]
    assert item["product"]["variation"]["attributes"]  # e.g. {"Colour": "Black"}


@pytest.mark.asyncio
async def test_simple_product_checkout_still_works(client, admin_headers):
    pid = await _simple_product(client, admin_headers, stock=10)
    response = await client.post(
        "/api/v1/checkout",
        json={**ADDRESS, "items": [{"productId": pid, "quantity": 3}]},
    )
    assert response.status_code == 200

    product = await client.get("/api/v1/products?pageSize=50")
    row = next(p for p in product.json()["items"] if p["id"] == pid)
    assert row["stock"] == 7


@pytest.mark.asyncio
async def test_attribute_filter_narrows_products(client, admin_headers, variable_product):
    await _simple_product(client, admin_headers)

    filtered = await client.get("/api/v1/products?attrs=black")
    ids = [p["id"] for p in filtered.json()["items"]]
    assert ids == [variable_product["product_id"]]


@pytest.mark.asyncio
async def test_variable_product_price_range_and_stock_are_derived(
    client, admin_headers, variable_product
):
    pid = variable_product["product_id"]
    vars_ = variable_product["variations"]

    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={
            "variations": [
                {"id": vars_[0]["id"], "price": 4000, "stock": 3},
                {"id": vars_[1]["id"], "price": 6000, "stock": 4},
            ]
        },
    )

    listed = await client.get("/api/v1/products?pageSize=50")
    row = next(p for p in listed.json()["items"] if p["id"] == pid)
    assert row["priceRange"] == {"min": 4000, "max": 6000}
    assert row["stock"] == 7  # summed, not the product column


@pytest.mark.asyncio
async def test_simple_product_has_no_price_range(client, admin_headers):
    pid = await _simple_product(client, admin_headers, stock=4, price=1500)
    listed = await client.get("/api/v1/products?pageSize=50")
    row = next(p for p in listed.json()["items"] if p["id"] == pid)
    assert row["priceRange"] is None
    assert row["price"] == 1500
    assert row["stock"] == 4


@pytest.mark.asyncio
async def test_deactivated_variation_excluded_from_derived_values(
    client, admin_headers, variable_product
):
    pid = variable_product["product_id"]
    vars_ = variable_product["variations"]
    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={
            "variations": [
                {"id": vars_[0]["id"], "price": 4000, "stock": 3, "isActive": False},
                {"id": vars_[1]["id"], "price": 6000, "stock": 4},
            ]
        },
    )

    listed = await client.get("/api/v1/products?pageSize=50")
    row = next(p for p in listed.json()["items"] if p["id"] == pid)
    assert row["priceRange"] == {"min": 6000, "max": 6000}
    assert row["stock"] == 4


# ── Order snapshot shows the variant actually bought ────────────


@pytest.mark.asyncio
async def test_order_snapshot_uses_the_purchased_variation_photo(
    client, admin_headers, variable_product
):
    """Product has no photos at all, both variations do — the order must
    show the one that was bought, not `_split_images`'s generic first-
    variation fallback used for cards and listings.
    """
    black_id = variable_product["variations"][0]["id"]
    tan_id = variable_product["variations"][1]["id"]
    pid = variable_product["product_id"]

    await client.post(
        f"/api/v1/admin/products/{pid}/variations/{black_id}/images",
        headers=admin_headers,
        json={"url": "https://cdn.test/black.jpg", "alt": "Black", "isFeatured": True},
    )
    await client.post(
        f"/api/v1/admin/products/{pid}/variations/{tan_id}/images",
        headers=admin_headers,
        json={"url": "https://cdn.test/tan.jpg", "alt": "Tan", "isFeatured": True},
    )

    checkout = await client.post(
        "/api/v1/checkout",
        json={
            **ADDRESS,
            "items": [{"productId": pid, "variationId": tan_id, "quantity": 1}],
        },
    )
    assert checkout.status_code == 200, checkout.text

    order = await client.get(
        f"/api/v1/admin/orders/{checkout.json()['id']}", headers=admin_headers
    )
    snapshot = order.json()["items"][0]["product"]
    assert snapshot["featuredImage"]["url"] == "https://cdn.test/tan.jpg"
    assert snapshot["variation"]["attributes"]["Colour"] == "Tan"


@pytest.mark.asyncio
async def test_order_snapshot_falls_back_when_variation_has_no_photo(
    client, admin_headers, variable_product
):
    """The purchased variation was never photographed — fall back to
    whatever the generic listing logic already provides, rather than null."""
    black_id = variable_product["variations"][0]["id"]
    pid = variable_product["product_id"]

    await client.post(
        f"/api/v1/admin/products/{pid}/variations/{black_id}/images",
        headers=admin_headers,
        json={"url": "https://cdn.test/black.jpg", "alt": "Black", "isFeatured": True},
    )

    tan_id = variable_product["variations"][1]["id"]
    checkout = await client.post(
        "/api/v1/checkout",
        json={
            **ADDRESS,
            "items": [{"productId": pid, "variationId": tan_id, "quantity": 1}],
        },
    )
    assert checkout.status_code == 200, checkout.text

    order = await client.get(
        f"/api/v1/admin/orders/{checkout.json()['id']}", headers=admin_headers
    )
    snapshot = order.json()["items"][0]["product"]
    # Falls back to Black's photo via the generic listing fallback, rather
    # than leaving the order with no image at all.
    assert snapshot["featuredImage"]["url"] == "https://cdn.test/black.jpg"
