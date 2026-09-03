"""Testimonial photo and verified-buyer fields.

Added because the storefront's home page carousel already reserved a big
photo slot next to every quote (see wrenza-app's TestimonialsSection), but
the backend had nowhere to store one — every testimonial rendered that slot
empty, permanently, regardless of what an admin set on the existing fields.
"""

import pytest


async def _create_testimonial(client, admin_headers, **overrides):
    payload = {
        "name": "Ayesha",
        "location": "Lahore, Pakistan",
        "comment": "Beautifully made, exactly as pictured.",
        "rating": 5,
        **overrides,
    }
    response = await client.post(
        "/api/v1/admin/testimonials", headers=admin_headers, json=payload
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_create_testimonial_with_image_and_verified_buyer(
    client, admin_headers
):
    created = await _create_testimonial(
        client,
        admin_headers,
        image="https://ik.imagekit.io/wrenza/testimonials/ayesha.jpg",
        isVerifiedBuyer=True,
    )
    assert created["image"] == "https://ik.imagekit.io/wrenza/testimonials/ayesha.jpg"
    assert created["isVerifiedBuyer"] is True


@pytest.mark.asyncio
async def test_testimonial_without_image_defaults_null_and_unverified(
    client, admin_headers
):
    created = await _create_testimonial(client, admin_headers)
    assert created["image"] is None
    assert created["isVerifiedBuyer"] is False


@pytest.mark.asyncio
async def test_public_testimonials_expose_image_and_verified_buyer(
    client, admin_headers
):
    await _create_testimonial(
        client,
        admin_headers,
        name="Bilal",
        image="https://ik.imagekit.io/wrenza/testimonials/bilal.jpg",
        isVerifiedBuyer=True,
    )

    response = await client.get("/api/v1/testimonials")
    assert response.status_code == 200, response.text
    body = response.json()
    bilal = next(t for t in body if t["name"] == "Bilal")
    assert bilal["image"] == "https://ik.imagekit.io/wrenza/testimonials/bilal.jpg"
    assert bilal["isVerifiedBuyer"] is True


@pytest.mark.asyncio
async def test_update_testimonial_can_set_image_and_verified_buyer(
    client, admin_headers
):
    created = await _create_testimonial(client, admin_headers)
    assert created["image"] is None

    response = await client.put(
        f"/api/v1/admin/testimonials/{created['id']}",
        headers=admin_headers,
        json={
            "name": created["name"],
            "comment": created["comment"],
            "rating": created["rating"],
            "image": "https://ik.imagekit.io/wrenza/testimonials/updated.jpg",
            "isVerifiedBuyer": True,
        },
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["image"] == "https://ik.imagekit.io/wrenza/testimonials/updated.jpg"
    assert updated["isVerifiedBuyer"] is True
