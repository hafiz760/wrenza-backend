import pytest

from app.db.models.product import Product
from app.db.models.user import Address
from app.db.models.wishlist import Wishlist
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_admin_can_view_customer_addresses_and_wishlist(
    client, admin_headers, test_user
):
    async with TestingSessionLocal() as db:
        product = Product(
            name="Test Wallet",
            slug="test-wallet-customer-detail",
            description="A wallet for the customer detail test.",
            price=4200,
        )
        db.add(product)
        await db.flush()

        db.add(
            Address(
                user_id=test_user.id,
                label="Home",
                street="12 Test Road",
                city="Lahore",
                state="Punjab",
                postal_code="54000",
                country="Pakistan",
                is_default=True,
            )
        )
        db.add(Wishlist(user_id=test_user.id, product_id=product.id))
        await db.commit()

    response = await client.get(
        f"/api/v1/admin/users/{test_user.id}", headers=admin_headers
    )

    assert response.status_code == 200
    detail = response.json()
    assert detail["email"] == test_user.email
    assert detail["addresses"][0] == {
        "id": detail["addresses"][0]["id"],
        "label": "Home",
        "street": "12 Test Road",
        "city": "Lahore",
        "state": "Punjab",
        "postalCode": "54000",
        "country": "Pakistan",
        "isDefault": True,
    }
    assert detail["wishlist"][0]["name"] == "Test Wallet"
    assert detail["wishlist"][0]["price"] == 4200.0
    assert detail["orders"] == []


@pytest.mark.asyncio
async def test_customer_detail_requires_admin(client, test_user):
    response = await client.get(f"/api/v1/admin/users/{test_user.id}")

    assert response.status_code == 401
