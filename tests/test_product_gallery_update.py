"""Gallery editing through `PUT /admin/products/{id}`.

The gallery used to be writable only via the separate image endpoints, so the
edit form could not manage it alongside everything else. It is now part of the
update payload, reconciled by URL.
"""

import pytest

IMAGE_A = "https://cdn.example.com/a.jpg"
IMAGE_B = "https://cdn.example.com/b.jpg"
IMAGE_C = "https://cdn.example.com/c.jpg"


async def _product(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Gallery Product",
            "description": "Leather.",
            "price": 1000,
            "images": [
                {"url": IMAGE_A, "alt": "A", "position": 0},
                {"url": IMAGE_B, "alt": "B", "position": 1},
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _update(client, admin_headers, product_id, payload):
    return await client.put(
        f"/api/v1/admin/products/{product_id}", headers=admin_headers, json=payload
    )


@pytest.mark.asyncio
async def test_images_without_dimensions_are_accepted(client, admin_headers):
    """ImageKit gives the dashboard a URL, not a width — sending {url, alt}
    alone used to raise KeyError and return a 500."""
    product = await _product(client, admin_headers)

    response = await _update(
        client,
        admin_headers,
        product["id"],
        {
            "featuredImage": {"url": IMAGE_C, "alt": "Hero"},
            "images": [{"url": IMAGE_A, "alt": "A"}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"]["url"] == IMAGE_C


@pytest.mark.asyncio
async def test_gallery_is_replaced_by_what_is_sent(client, admin_headers):
    product = await _product(client, admin_headers)

    response = await _update(
        client,
        admin_headers,
        product["id"],
        {"images": [{"url": IMAGE_C, "alt": "C"}, {"url": IMAGE_A, "alt": "A"}]},
    )
    assert response.status_code == 200, response.text

    # Order follows the list, and the image that was dropped is gone
    assert [i["url"] for i in response.json()["images"]] == [IMAGE_C, IMAGE_A]


@pytest.mark.asyncio
async def test_unchanged_images_keep_their_ids(client, admin_headers):
    """Reconciled rather than wiped and rebuilt, so ids survive a reorder."""
    product = await _product(client, admin_headers)
    original = {i["url"]: i["id"] for i in product["images"]}

    response = await _update(
        client,
        admin_headers,
        product["id"],
        {"images": [{"url": IMAGE_B, "alt": "B"}, {"url": IMAGE_A, "alt": "A"}]},
    )
    assert response.status_code == 200, response.text

    updated = {i["url"]: i["id"] for i in response.json()["images"]}
    assert updated[IMAGE_A] == original[IMAGE_A]
    assert updated[IMAGE_B] == original[IMAGE_B]


@pytest.mark.asyncio
async def test_omitting_images_leaves_the_gallery_alone(client, admin_headers):
    """A partial update that says nothing about images must not clear them."""
    product = await _product(client, admin_headers)

    response = await _update(
        client, admin_headers, product["id"], {"name": "Renamed Only"}
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["images"]) == 2


@pytest.mark.asyncio
async def test_empty_list_clears_the_gallery(client, admin_headers):
    product = await _product(client, admin_headers)

    response = await _update(client, admin_headers, product["id"], {"images": []})
    assert response.status_code == 200, response.text
    assert response.json()["images"] == []


@pytest.mark.asyncio
async def test_replacing_the_feature_image_does_not_touch_the_gallery(
    client, admin_headers
):
    product = await _product(client, admin_headers)

    response = await _update(
        client,
        admin_headers,
        product["id"],
        {"featuredImage": {"url": IMAGE_C, "alt": "Hero"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["featuredImage"]["url"] == IMAGE_C
    assert [i["url"] for i in response.json()["images"]] == [IMAGE_A, IMAGE_B]
