"""Public product endpoints the storefront depends on.

Covers the payload additions made so the storefront can drop its mock data:
FAQs on the detail, a public review list with a rating histogram, and the
catalog filter facets.
"""

import pytest


async def _product(client, admin_headers, name="Heritage Bifold", **extra):
    body = {"name": name, "description": "Full grain leather.", "price": 4500}
    body.update(extra)
    response = await client.post(
        "/api/v1/admin/products", headers=admin_headers, json=body
    )
    assert response.status_code == 200, response.text
    return response.json()


# ── FAQs on the public payload ──────────────────────────────────


@pytest.mark.asyncio
async def test_public_detail_includes_faqs_in_position_order(client, admin_headers):
    """The FAQPage schema quotes these, so order and content must match."""
    product = await _product(client, admin_headers)

    await client.put(
        f"/api/v1/admin/products/{product['id']}/faqs",
        headers=admin_headers,
        json={
            "faqs": [
                {"question": "Is it genuine leather?", "answer": "Yes, full grain."},
                {"question": "Does it fit coins?", "answer": "No, cards and notes."},
            ]
        },
    )

    body = (await client.get(f"/api/v1/products/{product['slug']}")).json()
    assert [f["question"] for f in body["faqs"]] == [
        "Is it genuine leather?",
        "Does it fit coins?",
    ]
    assert body["faqs"][0]["answer"] == "Yes, full grain."


@pytest.mark.asyncio
async def test_public_detail_faqs_default_empty(client, admin_headers):
    product = await _product(client, admin_headers, name="No Faq Wallet")
    body = (await client.get(f"/api/v1/products/{product['slug']}")).json()
    assert body["faqs"] == []


# ── Public reviews ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_public_reviews_returns_items_and_histogram(
    client, admin_headers, auth_headers
):
    product = await _product(client, admin_headers, name="Reviewed Wallet")

    created = await client.post(
        "/api/v1/reviews",
        headers=auth_headers,
        json={"productId": product["id"], "rating": 4, "comment": "Very good."},
    )
    assert created.status_code == 200, created.text

    # Reviews are created pending — anyone can post one, so nothing reaches
    # the storefront until an admin approves it.
    approved = await client.put(
        f"/api/v1/admin/reviews/{created.json()['id']}/approve?approved=true",
        headers=admin_headers,
    )
    assert approved.status_code == 200, approved.text

    response = await client.get(f"/api/v1/products/{product['slug']}/reviews")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["rating"] == 4
    assert body["items"][0]["comment"] == "Very good."
    assert body["items"][0]["userName"].strip()

    assert body["summary"]["average"] == 4.0
    assert body["summary"]["total"] == 1
    # Every bucket present, so the histogram never has holes to guard against
    assert body["summary"]["distribution"] == {
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 1,
        "5": 0,
    }


@pytest.mark.asyncio
async def test_public_reviews_empty_product(client, admin_headers):
    product = await _product(client, admin_headers, name="Unreviewed Wallet")
    body = (await client.get(f"/api/v1/products/{product['slug']}/reviews")).json()

    assert body["total"] == 0
    assert body["items"] == []
    assert body["summary"]["average"] == 0.0
    assert body["summary"]["distribution"] == {str(n): 0 for n in range(1, 6)}


@pytest.mark.asyncio
async def test_public_reviews_unknown_slug_is_404(client):
    response = await client.get("/api/v1/products/no-such-product/reviews")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reviews_route_not_shadowed_by_slug_route(client, admin_headers):
    """`/{slug}` is declared after `/{slug}/reviews`; confirm it stays that way."""
    product = await _product(client, admin_headers, name="Shadow Test")
    detail = await client.get(f"/api/v1/products/{product['slug']}")
    reviews = await client.get(f"/api/v1/products/{product['slug']}/reviews")

    assert "faqs" in detail.json()
    assert "summary" in reviews.json()


# ── Filter facets ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filters_counts_match_what_filtering_returns(client, admin_headers):
    """A term advertising N products must return N when actually applied."""
    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Colour"}
    )
    attr_id = attr.json()["id"]
    term = await client.post(
        f"/api/v1/admin/attributes/{attr_id}/terms",
        headers=admin_headers,
        json={"value": "Black"},
    )
    term_id = term.json()["id"]

    for name in ("Black Wallet", "Black Belt"):
        product = await _product(client, admin_headers, name=name)
        await client.put(
            f"/api/v1/admin/products/{product['id']}/attributes",
            headers=admin_headers,
            json={
                "attributes": [
                    {
                        "attributeId": attr_id,
                        "termIds": [term_id],
                        "usedForVariations": False,
                    }
                ]
            },
        )

    filters = (await client.get("/api/v1/products/filters")).json()
    colour = next(a for a in filters["attributes"] if a["name"] == "Colour")
    black = next(t for t in colour["terms"] if t["value"] == "Black")

    assert black["productCount"] == 2

    listed = (await client.get(f"/api/v1/products?attrs={black['slug']}")).json()
    assert listed["total"] == black["productCount"]


@pytest.mark.asyncio
async def test_filters_omit_terms_no_product_offers(client, admin_headers):
    """An option that returns nothing is a dead end, so it is not advertised."""
    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Finish"}
    )
    await client.post(
        f"/api/v1/admin/attributes/{attr.json()['id']}/terms",
        headers=admin_headers,
        json={"value": "Unused"},
    )

    filters = (await client.get("/api/v1/products/filters")).json()
    offered = {t["value"] for a in filters["attributes"] for t in a["terms"]}
    assert "Unused" not in offered


@pytest.mark.asyncio
async def test_filters_report_price_bounds(client, admin_headers):
    await _product(client, admin_headers, name="Cheap", price=1000)
    await _product(client, admin_headers, name="Dear", price=9000)

    filters = (await client.get("/api/v1/products/filters")).json()
    assert filters["price"]["min"] == 1000
    assert filters["price"]["max"] == 9000


@pytest.mark.asyncio
async def test_filters_route_not_treated_as_a_slug(client):
    """`/products/filters` must hit the facets route, not the detail route."""
    response = await client.get("/api/v1/products/filters")
    assert response.status_code == 200
    assert "attributes" in response.json()
