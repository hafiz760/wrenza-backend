"""Reviews from visitors without an account.

The storefront accepts reviews from anyone, matching how the Shopify review
apps behave: requiring a login or a matching order would mean almost no reviews
on a young catalogue. Nothing is trusted on submission — every review is
created pending and only an admin approval puts it on the product page.

Two things here guard real exposure. Guest email must never appear in the
public payload, and a guest review must not vanish from the listing: the
listing used an inner join on `users`, which silently dropped every review
without an account while still counting it in the histogram.
"""

import pytest


async def _product(client, admin_headers, name="Curve Wallet"):
    response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": name,
            "description": "A wallet.",
            "price": 2650,
            "stock": 10,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _post_review(client, product_id, headers=None, **extra):
    body = {"productId": product_id, "rating": 5, "comment": "Lovely leather."}
    body.update(extra)
    return await client.post(
        "/api/v1/reviews", headers=headers or {}, json=body
    )


# ── Guests can review ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_guest_can_review_without_an_account(client, admin_headers):
    product = await _product(client, admin_headers)

    response = await _post_review(
        client, product["id"], name="Khurram Ijaz", email="khurram@example.com"
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["userName"] == "Khurram Ijaz"
    assert body["userId"] is None


@pytest.mark.asyncio
async def test_guest_review_requires_name_and_email(client, admin_headers):
    product = await _product(client, admin_headers)

    response = await _post_review(client, product["id"])
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_signed_in_review_still_works(client, admin_headers, auth_headers):
    product = await _product(client, admin_headers)

    response = await _post_review(client, product["id"], headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["userId"] is not None


@pytest.mark.asyncio
async def test_account_name_wins_over_submitted_name(
    client, admin_headers, auth_headers
):
    """A signed-in reviewer must not be able to post under another name."""
    product = await _product(client, admin_headers)

    response = await _post_review(
        client, product["id"], headers=auth_headers, name="Someone Else"
    )
    assert response.status_code == 200, response.text
    assert response.json()["userName"] != "Someone Else"


# ── Moderation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_review_is_pending_and_hidden(client, admin_headers):
    """Anyone can post, so nothing is public until approved."""
    product = await _product(client, admin_headers)
    await _post_review(
        client, product["id"], name="Khurram", email="k@example.com"
    )

    response = await client.get(f"/api/v1/products/{product['slug']}/reviews")
    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["summary"]["total"] == 0


@pytest.mark.asyncio
async def test_pending_review_does_not_move_the_product_rating(
    client, admin_headers
):
    product = await _product(client, admin_headers)
    await _post_review(
        client, product["id"], name="Khurram", email="k@example.com", rating=5
    )

    response = await client.get(f"/api/v1/products/{product['slug']}")
    assert response.status_code == 200, response.text
    assert response.json()["rating"] == 0
    assert response.json()["reviewCount"] == 0


@pytest.mark.asyncio
async def test_guest_review_appears_once_approved(client, admin_headers):
    """The inner-join bug: approved guest reviews were counted but not listed."""
    product = await _product(client, admin_headers)
    created = await _post_review(
        client, product["id"], name="Khurram Ijaz", email="k@example.com"
    )
    review_id = created.json()["id"]

    approve = await client.put(
        f"/api/v1/admin/reviews/{review_id}/approve?approved=true",
        headers=admin_headers,
    )
    assert approve.status_code == 200, approve.text

    response = await client.get(f"/api/v1/products/{product['slug']}/reviews")
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert len(payload["items"]) == 1, "guest review counted but not listed"
    assert payload["items"][0]["userName"] == "Khurram Ijaz"


# ── The guest's email is not public ─────────────────────────────


@pytest.mark.asyncio
async def test_guest_email_is_never_public(client, admin_headers):
    product = await _product(client, admin_headers)
    created = await _post_review(
        client, product["id"], name="Khurram", email="private@example.com"
    )
    assert "private@example.com" not in created.text

    approve_id = created.json()["id"]
    await client.put(
        f"/api/v1/admin/reviews/{approve_id}/approve?approved=true",
        headers=admin_headers,
    )

    response = await client.get(f"/api/v1/products/{product['slug']}/reviews")
    assert "private@example.com" not in response.text


@pytest.mark.asyncio
async def test_admin_sees_the_guest_email(client, admin_headers):
    """Admins need it to spot abuse; it is the one place it is exposed."""
    product = await _product(client, admin_headers)
    await _post_review(
        client, product["id"], name="Khurram", email="private@example.com"
    )

    response = await client.get("/api/v1/admin/reviews", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["customerEmail"] == "private@example.com"
    assert response.json()["items"][0]["isGuest"] is True
