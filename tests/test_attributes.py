import pytest
import pytest_asyncio

from app.db.models.attribute import Attribute, AttributeTerm
from tests.conftest import TestingSessionLocal


@pytest.mark.asyncio
async def test_attribute_and_terms_persist():
    from sqlalchemy import select

    async with TestingSessionLocal() as db:
        attr = Attribute(name="Leather Color", slug="leather-color", position=0)
        db.add(attr)
        await db.flush()

        db.add(
            AttributeTerm(
                attribute_id=attr.id,
                value="Black",
                slug="black",
                meta={"hex": "#000000"},
                position=0,
            )
        )
        await db.commit()

        loaded = await db.scalar(select(Attribute).filter(Attribute.id == attr.id))
        assert loaded.name == "Leather Color"
        assert loaded.is_filterable is True
        assert len(loaded.terms) == 1
        assert loaded.terms[0].meta["hex"] == "#000000"


@pytest.mark.asyncio
async def test_term_slug_unique_within_attribute_only():
    """Same term slug is allowed under two different attributes."""
    from sqlalchemy.exc import IntegrityError

    async with TestingSessionLocal() as db:
        a1 = Attribute(name="Leather Color", slug="leather-color")
        a2 = Attribute(name="Thread Color", slug="thread-color")
        db.add_all([a1, a2])
        await db.flush()

        db.add(AttributeTerm(attribute_id=a1.id, value="Black", slug="black"))
        db.add(AttributeTerm(attribute_id=a2.id, value="Black", slug="black"))
        await db.commit()  # different attributes -> allowed

        db.add(AttributeTerm(attribute_id=a1.id, value="Black Again", slug="black"))
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.asyncio
async def test_create_attribute_generates_slug(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/attributes",
        headers=admin_headers,
        json={"name": "Leather Color"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Leather Color"
    assert data["slug"] == "leather-color"
    assert data["isFilterable"] is True
    assert data["terms"] == []


@pytest.mark.asyncio
async def test_duplicate_attribute_name_gets_unique_slug(client, admin_headers):
    await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Size"}
    )
    second = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Size"}
    )
    assert second.status_code == 200
    assert second.json()["slug"] == "size-1"


@pytest.mark.asyncio
async def test_attribute_requires_admin(client, auth_headers):
    response = await client.post(
        "/api/v1/admin/attributes", headers=auth_headers, json={"name": "Size"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_and_delete_attribute(client, admin_headers):
    created = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Size"}
    )
    attr_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/admin/attributes/{attr_id}",
        headers=admin_headers,
        json={"name": "Belt Size", "isFilterable": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Belt Size"
    assert updated.json()["isFilterable"] is False

    deleted = await client.delete(
        f"/api/v1/admin/attributes/{attr_id}", headers=admin_headers
    )
    assert deleted.status_code == 200

    listed = await client.get("/api/v1/admin/attributes", headers=admin_headers)
    assert listed.json() == []


@pytest.mark.asyncio
async def test_update_missing_attribute_returns_404(client, admin_headers):
    response = await client.put(
        "/api/v1/admin/attributes/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
        json={"name": "Nope"},
    )
    assert response.status_code == 404


@pytest_asyncio.fixture
async def color_attribute(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/attributes",
        headers=admin_headers,
        json={"name": "Leather Color"},
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_term_with_swatch(client, admin_headers, color_attribute):
    response = await client.post(
        f"/api/v1/admin/attributes/{color_attribute}/terms",
        headers=admin_headers,
        json={"value": "Black", "meta": {"hex": "#000000"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Black"
    assert data["slug"] == "black"
    assert data["meta"]["hex"] == "#000000"


@pytest.mark.asyncio
async def test_terms_appear_on_parent_attribute(
    client, admin_headers, color_attribute
):
    for value in ("Black", "Tan"):
        await client.post(
            f"/api/v1/admin/attributes/{color_attribute}/terms",
            headers=admin_headers,
            json={"value": value},
        )

    listed = await client.get("/api/v1/admin/attributes", headers=admin_headers)
    terms = listed.json()[0]["terms"]
    assert [t["slug"] for t in terms] == ["black", "tan"]


@pytest.mark.asyncio
async def test_duplicate_term_slug_within_attribute_is_suffixed(
    client, admin_headers, color_attribute
):
    first = await client.post(
        f"/api/v1/admin/attributes/{color_attribute}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    second = await client.post(
        f"/api/v1/admin/attributes/{color_attribute}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    assert first.json()["slug"] == "black"
    assert second.json()["slug"] == "black-1"


@pytest.mark.asyncio
async def test_term_on_missing_attribute_returns_404(client, admin_headers):
    response = await client.post(
        "/api/v1/admin/attributes/00000000-0000-0000-0000-000000000000/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_and_delete_term(client, admin_headers, color_attribute):
    created = await client.post(
        f"/api/v1/admin/attributes/{color_attribute}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    term_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/admin/attributes/{color_attribute}/terms/{term_id}",
        headers=admin_headers,
        json={"value": "Jet Black", "meta": {"hex": "#111111"}},
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == "Jet Black"

    deleted = await client.delete(
        f"/api/v1/admin/attributes/{color_attribute}/terms/{term_id}",
        headers=admin_headers,
    )
    assert deleted.status_code == 200

    listed = await client.get("/api/v1/admin/attributes", headers=admin_headers)
    assert listed.json()[0]["terms"] == []


@pytest.mark.asyncio
async def test_term_operations_scoped_to_owning_attribute_404(client, admin_headers):
    first = await client.post(
        "/api/v1/admin/attributes",
        headers=admin_headers,
        json={"name": "Leather Color"},
    )
    second = await client.post(
        "/api/v1/admin/attributes",
        headers=admin_headers,
        json={"name": "Thread Color"},
    )
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    created = await client.post(
        f"/api/v1/admin/attributes/{first_id}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    term_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/admin/attributes/{second_id}/terms/{term_id}",
        headers=admin_headers,
        json={"value": "Jet Black"},
    )
    assert updated.status_code == 404

    deleted = await client.delete(
        f"/api/v1/admin/attributes/{second_id}/terms/{term_id}",
        headers=admin_headers,
    )
    assert deleted.status_code == 404


@pytest.mark.asyncio
async def test_deleting_attribute_cascades_to_terms(
    client, admin_headers, color_attribute
):
    from sqlalchemy import select

    from app.db.models.attribute import AttributeTerm

    await client.post(
        f"/api/v1/admin/attributes/{color_attribute}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    await client.delete(
        f"/api/v1/admin/attributes/{color_attribute}", headers=admin_headers
    )

    async with TestingSessionLocal() as db:
        remaining = (await db.execute(select(AttributeTerm))).scalars().all()
        assert remaining == []
