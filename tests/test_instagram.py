"""Instagram media mirroring.

`_fetch_media` and `_call_refresh_endpoint` are monkeypatched out — real
network calls to Instagram's Graph API, not something this suite should
depend on being reachable — matching how `test_safepay.py` handles its own
third-party gateway calls.
"""

from types import SimpleNamespace

import pytest

from app.services import instagram_service


@pytest.fixture
def configured_settings(monkeypatch):
    """Points instagram_service at a business id without touching the
    process-wide lru_cache'd Settings singleton other tests rely on."""
    fake_settings = SimpleNamespace(INSTAGRAM_BUSINESS_ID="17841480302328569")
    monkeypatch.setattr(instagram_service, "get_settings", lambda: fake_settings)


@pytest.fixture(autouse=True)
def no_env_token(monkeypatch):
    """Blocks `settings_service`'s .env-seed on a fresh row.

    A real INSTAGRAM_ACCESS_TOKEN lives in the dev .env for production use;
    without this, every "nothing configured yet" test would pass or fail
    depending on whether that value happens to be set on the machine
    running the suite.
    """
    from app.services import settings_service

    fake_env = SimpleNamespace(INSTAGRAM_ACCESS_TOKEN="")
    monkeypatch.setattr(settings_service, "get_settings", lambda: fake_env)


async def _set_stored_token(token: str | None):
    from tests.conftest import TestingSessionLocal
    from app.services import settings_service

    async with TestingSessionLocal() as db:
        settings = await settings_service.get_or_create(db)
        settings.instagram_access_token = token
        await db.commit()


@pytest.mark.asyncio
async def test_media_empty_when_no_token_configured(client):
    response = await client.get("/api/v1/instagram/media")
    assert response.status_code == 200
    assert response.json() == {"data": []}


@pytest.mark.asyncio
async def test_media_empty_when_business_id_missing(client, monkeypatch):
    await _set_stored_token("a-token")
    monkeypatch.setattr(
        instagram_service, "get_settings", lambda: SimpleNamespace(INSTAGRAM_BUSINESS_ID="")
    )

    response = await client.get("/api/v1/instagram/media")
    assert response.json() == {"data": []}


@pytest.mark.asyncio
async def test_media_fetches_and_trims_fields(client, configured_settings, monkeypatch):
    await _set_stored_token("a-token")

    async def fake_fetch_media(business_id, access_token):
        assert business_id == "17841480302328569"
        assert access_token == "a-token"
        return [
            {
                "id": "1",
                "caption": "Line one\nLine two with #hashtags",
                "media_type": "VIDEO",
                "media_url": "https://cdn.example.com/video.mp4",
                "thumbnail_url": "https://cdn.example.com/thumb.jpg",
                "permalink": "https://instagram.com/reel/abc/",
                "timestamp": "2026-08-29T14:05:10+0000",
            },
            {
                # No media_url/thumbnail_url at all — dropped, not surfaced
                # as a broken tile on the homepage.
                "id": "2",
                "caption": "No media",
                "media_type": "VIDEO",
                "permalink": "https://instagram.com/reel/def/",
                "timestamp": "2026-08-20T14:01:54+0000",
            },
        ]

    monkeypatch.setattr(instagram_service, "_fetch_media", fake_fetch_media)

    response = await client.get("/api/v1/instagram/media")
    assert response.status_code == 200
    data = response.json()["data"]

    assert len(data) == 1
    item = data[0]
    assert item["id"] == "1"
    assert item["mediaType"] == "VIDEO"
    # Poster frame preferred over the raw video file for a static grid.
    assert item["mediaUrl"] == "https://cdn.example.com/thumb.jpg"
    assert item["caption"] == "Line one"
    assert item["permalink"] == "https://instagram.com/reel/abc/"


@pytest.mark.asyncio
async def test_video_without_thumbnail_is_dropped_not_shown_as_broken_image(
    client, configured_settings, monkeypatch
):
    await _set_stored_token("a-token")

    async def fake_fetch_media(business_id, access_token):
        return [
            {
                "id": "1",
                "media_type": "VIDEO",
                # No thumbnail_url — the raw .mp4 in media_url must never be
                # used as the tile's <img> src.
                "media_url": "https://cdn.example.com/raw-video.mp4",
                "permalink": "https://instagram.com/reel/nopreview/",
                "timestamp": "2026-08-29T14:05:10+0000",
            },
            {
                "id": "2",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example.com/photo.jpg",
                "permalink": "https://instagram.com/p/photo/",
                "timestamp": "2026-08-29T14:05:10+0000",
            },
        ]

    monkeypatch.setattr(instagram_service, "_fetch_media", fake_fetch_media)

    response = await client.get("/api/v1/instagram/media")
    data = response.json()["data"]

    assert len(data) == 1
    assert data[0]["id"] == "2"
    assert data[0]["mediaUrl"] == "https://cdn.example.com/photo.jpg"


@pytest.mark.asyncio
async def test_media_is_cached_across_requests(client, configured_settings, monkeypatch):
    await _set_stored_token("a-token")
    calls = 0

    async def fake_fetch_media(business_id, access_token):
        nonlocal calls
        calls += 1
        return [
            {
                "id": "1",
                "media_type": "IMAGE",
                "media_url": "https://cdn.example.com/1.jpg",
                "permalink": "https://instagram.com/p/1/",
                "timestamp": "2026-08-29T14:05:10+0000",
            }
        ]

    monkeypatch.setattr(instagram_service, "_fetch_media", fake_fetch_media)

    first = await client.get("/api/v1/instagram/media")
    second = await client.get("/api/v1/instagram/media")

    assert first.json() == second.json()
    assert calls == 1


@pytest.mark.asyncio
async def test_media_fails_open_on_api_error(client, configured_settings, monkeypatch):
    import httpx

    await _set_stored_token("a-token")

    async def fake_fetch_media(business_id, access_token):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(instagram_service, "_fetch_media", fake_fetch_media)

    response = await client.get("/api/v1/instagram/media")
    assert response.status_code == 200
    assert response.json() == {"data": []}


@pytest.mark.asyncio
async def test_refresh_token_updates_stored_token():
    from tests.conftest import TestingSessionLocal
    from app.services import settings_service

    await _set_stored_token("old-token")

    async def fake_refresh_endpoint(access_token):
        assert access_token == "old-token"
        return "new-token"

    import pytest as _pytest  # local import keeps monkeypatch scoped simply
    mp = _pytest.MonkeyPatch()
    mp.setattr(instagram_service, "_call_refresh_endpoint", fake_refresh_endpoint)
    try:
        async with TestingSessionLocal() as db:
            result = await instagram_service.refresh_token(db)
            assert result is True

        async with TestingSessionLocal() as db:
            settings = await settings_service.get_or_create(db)
            assert settings.instagram_access_token == "new-token"
            assert settings.instagram_token_refreshed_at is not None
    finally:
        mp.undo()


@pytest.mark.asyncio
async def test_refresh_token_leaves_token_untouched_on_failure():
    from tests.conftest import TestingSessionLocal
    from app.services import settings_service
    import httpx

    await _set_stored_token("old-token")

    async def failing_refresh_endpoint(access_token):
        raise httpx.HTTPError("boom")

    mp = pytest.MonkeyPatch()
    mp.setattr(instagram_service, "_call_refresh_endpoint", failing_refresh_endpoint)
    try:
        async with TestingSessionLocal() as db:
            result = await instagram_service.refresh_token(db)
            assert result is False

        async with TestingSessionLocal() as db:
            settings = await settings_service.get_or_create(db)
            assert settings.instagram_access_token == "old-token"
    finally:
        mp.undo()


@pytest.mark.asyncio
async def test_refresh_token_noop_when_nothing_stored():
    from tests.conftest import TestingSessionLocal

    async with TestingSessionLocal() as db:
        result = await instagram_service.refresh_token(db)

    assert result is False
