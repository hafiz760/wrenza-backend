import pytest

IMG = "https://ik.imagekit.io/demo/banner.jpg"
VID = "https://ik.imagekit.io/demo/banner.mov/ik-video.mp4"


@pytest.mark.asyncio
async def test_image_banner_has_no_video(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/banners",
        headers=admin_headers,
        json={"title": "Summer Sale", "imageUrl": IMG},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["videoUrl"] is None
    assert data["mediaType"] == "image"


@pytest.mark.asyncio
async def test_video_banner_keeps_poster_image(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/banners",
        headers=admin_headers,
        json={"title": "Launch Film", "imageUrl": IMG, "videoUrl": VID},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["videoUrl"] == VID
    assert data["imageUrl"] == IMG  # poster still required
    assert data["mediaType"] == "video"


@pytest.mark.asyncio
async def test_video_banner_requires_poster(client, admin_headers):
    """image_url stays mandatory — mobile shows it when autoplay is blocked."""
    response = await client.post(
        "/api/v1/admin/banners",
        headers=admin_headers,
        json={"title": "No Poster", "videoUrl": VID},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_can_add_video_to_existing_banner(client, admin_headers):
    created = await client.post(
        "/api/v1/admin/banners",
        headers=admin_headers,
        json={"title": "Grows Up", "imageUrl": IMG},
    )
    banner_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/admin/banners/{banner_id}",
        headers=admin_headers,
        json={"videoUrl": VID},
    )
    assert updated.status_code == 200
    assert updated.json()["mediaType"] == "video"


@pytest.mark.asyncio
async def test_public_banner_list_exposes_video(client, admin_headers):
    await client.post(
        "/api/v1/admin/banners",
        headers=admin_headers,
        json={"title": "Public", "imageUrl": IMG, "videoUrl": VID},
    )
    response = await client.get("/api/v1/banners")
    assert response.status_code == 200
    row = response.json()[0]
    assert row["videoUrl"] == VID
    assert row["mediaType"] == "video"


@pytest.mark.asyncio
async def test_banner_requires_admin(client, auth_headers):
    response = await client.post(
        "/api/v1/admin/banners",
        headers=auth_headers,
        json={"title": "Nope", "imageUrl": IMG},
    )
    assert response.status_code == 403
