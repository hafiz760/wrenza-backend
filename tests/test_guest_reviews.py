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
async def test_review_accepts_up_to_three_imagekit_photos(client, admin_headers):
    product = await _product(client, admin_headers)
    images = [
        f"https://ik.imagekit.io/ghio91g6p/reviews/customer-{index}.webp"
        for index in range(3)
    ]

    response = await _post_review(
        client,
        product["id"],
        name="Photo reviewer",
        email="photos@example.com",
        images=images,
    )

    assert response.status_code == 200, response.text
    assert response.json()["images"] == images


@pytest.mark.asyncio
async def test_review_rejects_more_than_three_or_non_imagekit_photos(
    client, admin_headers
):
    product = await _product(client, admin_headers)
    too_many = await _post_review(
        client,
        product["id"],
        name="Photo reviewer",
        email="photos@example.com",
        images=[f"https://ik.imagekit.io/ghio91g6p/reviews/{index}.jpg" for index in range(4)],
    )
    external_host = await _post_review(
        client,
        product["id"],
        name="Photo reviewer",
        email="photos@example.com",
        images=["https://example.com/not-imagekit.jpg"],
    )

    assert too_many.status_code == 422
    assert external_host.status_code == 422


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

    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["rating"] == 5
    assert detail.json()["reviewCount"] == 1

    hide = await client.put(
        f"/api/v1/admin/reviews/{review_id}/approve?approved=false",
        headers=admin_headers,
    )
    assert hide.status_code == 200, hide.text
    detail = await client.get(f"/api/v1/products/{product['slug']}")
    assert detail.json()["rating"] == 0
    assert detail.json()["reviewCount"] == 0


@pytest.mark.asyncio
async def test_approved_review_photos_feed_contains_only_approved_reviews(
    client, admin_headers
):
    product = await _product(client, admin_headers)
    created = await _post_review(
        client,
        product["id"],
        name="Photo reviewer",
        email="photos@example.com",
        images=[
            "https://ik.imagekit.io/ghio91g6p/reviews/customer-1.webp",
            "https://ik.imagekit.io/ghio91g6p/reviews/customer-2.webp",
        ],
    )

    hidden = await client.get("/api/v1/review-photos")
    assert hidden.status_code == 200
    assert hidden.json() == []

    await client.put(
        f"/api/v1/admin/reviews/{created.json()['id']}/approve?approved=true",
        headers=admin_headers,
    )
    visible = await client.get("/api/v1/review-photos")

    assert visible.status_code == 200, visible.text
    assert len(visible.json()) == 1
    assert visible.json()[0]["images"] == [
        "https://ik.imagekit.io/ghio91g6p/reviews/customer-1.webp",
        "https://ik.imagekit.io/ghio91g6p/reviews/customer-2.webp",
    ]
    assert visible.json()[0]["productSlug"] == product["slug"]


@pytest.mark.asyncio
async def test_homepage_review_photo_feed_returns_approved_reviews_with_all_ratings(
    client, admin_headers
):
    product = await _product(client, admin_headers)
    low_rated = await _post_review(
        client,
        product["id"],
        name="Three star reviewer",
        email="three@example.com",
        rating=3,
        images=["https://ik.imagekit.io/ghio91g6p/reviews/three-star.webp"],
    )
    high_rated = await _post_review(
        client,
        product["id"],
        name="Four star reviewer",
        email="four@example.com",
        rating=4,
        images=["https://ik.imagekit.io/ghio91g6p/reviews/four-star.webp"],
    )

    for review in (low_rated, high_rated):
        await client.put(
            f"/api/v1/admin/reviews/{review.json()['id']}/approve?approved=true",
            headers=admin_headers,
        )

    response = await client.get("/api/v1/review-photos")

    assert response.status_code == 200, response.text
    assert {photo["rating"] for photo in response.json()} == {3, 4}
    assert len(response.json()) == 2


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
