import pytest


@pytest.mark.asyncio
async def test_list_products_empty(client):
    response = await client.get("/api/v1/products")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["pageSize"] == 12
    assert data["totalPages"] == 0


@pytest.mark.asyncio
async def test_create_and_list_product(client, admin_headers):
    # Admin creates a product
    create_response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Pastel Rose Chiffon Kurta",
            "description": "Beautiful pastel rose chiffon kurta for casual wear.",
            "price": 5200,
            "compareAtPrice": 6800,
            "sizes": [
                {"label": "S", "value": "s", "inStock": True},
                {"label": "M", "value": "m", "inStock": True},
                {"label": "L", "value": "l", "inStock": True},
            ],
            "colors": [
                {"name": "Rose", "hex": "#E8B4B8", "inStock": True},
            ],
            "stock": 30,
            "isFeatured": True,
            "isNewArrival": True,
            "careInstructions": ["Dry clean only", "Iron on low heat"],
            "tags": ["casual", "chiffon"],
            "images": [
                {
                    "url": "https://example.com/image1.webp",
                    "alt": "Rose Kurta Front",
                    "width": 800,
                    "height": 1200,
                },
            ],
        },
    )
    assert create_response.status_code == 200
    product = create_response.json()
    assert product["name"] == "Pastel Rose Chiffon Kurta"
    assert product["slug"] == "pastel-rose-chiffon-kurta"
    assert product["price"] == 5200.0
    assert product["compareAtPrice"] == 6800.0

    # Public list should show the product
    list_response = await client.get("/api/v1/products")
    data = list_response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Pastel Rose Chiffon Kurta"


@pytest.mark.asyncio
async def test_get_product_by_slug(client, admin_headers):
    # Create a product first
    await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Royal Blue Silk Kurta",
            "description": "Elegant royal blue silk kurta.",
            "price": 8500,
            "stock": 15,
        },
    )

    response = await client.get("/api/v1/products/royal-blue-silk-kurta")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Royal Blue Silk Kurta"
    assert "description" in data
    assert "careInstructions" in data


@pytest.mark.asyncio
async def test_get_featured_products(client, admin_headers):
    await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Featured Kurta",
            "description": "A featured product.",
            "price": 3000,
            "stock": 10,
            "isFeatured": True,
        },
    )

    response = await client.get("/api/v1/products/featured")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_product_not_found(client):
    response = await client.get("/api/v1/products/nonexistent-slug")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_product_unauthorized(client):
    response = await client.post(
        "/api/v1/admin/products",
        json={"name": "Test", "description": "Test", "price": 1000, "stock": 10},
    )
    assert response.status_code == 401
