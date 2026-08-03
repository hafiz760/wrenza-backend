import pytest


@pytest.mark.asyncio
async def test_place_order(client, auth_headers, admin_headers):
    # Admin creates a product
    product_response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Order Test Kurta",
            "description": "A kurta for testing orders.",
            "price": 4500,
            "stock": 20,
            "sizes": [{"label": "M", "value": "m", "inStock": True}],
            "colors": [{"name": "Blue", "hex": "#0000FF", "inStock": True}],
        },
    )
    product = product_response.json()

    # Customer places order
    order_response = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "items": [
                {
                    "productId": product["id"],
                    "quantity": 2,
                    "size": "M",
                    "color": "Blue",
                }
            ],
            "shippingAddress": {
                "label": "Home",
                "street": "House 42, Street 7",
                "city": "Lahore",
                "state": "Punjab",
                "postalCode": "54000",
                "country": "Pakistan",
            },
            "phone": "+92 300 1234567",
        },
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["orderNumber"].startswith("KK-")
    assert order["status"] == "pending"
    assert order["paymentMethod"] == "Cash on Delivery"
    assert order["subtotal"] == 9000.0  # 4500 * 2
    assert order["shipping"] == 0.0  # Free shipping (>5000)
    assert order["total"] == 9000.0
    assert len(order["items"]) == 1


@pytest.mark.asyncio
async def test_list_my_orders(client, auth_headers):
    response = await client.get("/api/v1/orders", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_place_order_unauthorized(client):
    response = await client.post(
        "/api/v1/orders",
        json={
            "items": [
                {"productId": "fake-id", "quantity": 1, "size": "M", "color": "Blue"}
            ],
            "shippingAddress": {
                "label": "Home",
                "street": "Street",
                "city": "City",
                "state": "State",
                "postalCode": "12345",
            },
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_shipping_cost_under_threshold(client, auth_headers, admin_headers):
    # Create a cheap product
    product_response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Cheap Kurta",
            "description": "Budget kurta.",
            "price": 2000,
            "stock": 50,
        },
    )
    product = product_response.json()

    # Place order under 5000 PKR
    order_response = await client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "items": [
                {
                    "productId": product["id"],
                    "quantity": 1,
                    "size": "M",
                    "color": "Black",
                }
            ],
            "shippingAddress": {
                "label": "Office",
                "street": "123 Main St",
                "city": "Karachi",
                "state": "Sindh",
                "postalCode": "75000",
            },
        },
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["subtotal"] == 2000.0
    assert order["shipping"] == 250.0  # Shipping charged (<5000)
    assert order["total"] == 2250.0
