import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def setup(client, admin_headers):
    """A variable product plus Colour(Black,Tan) and Hardware(Silver)."""
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Bifold Wallet",
            "description": "Full grain leather bifold.",
            "kind": "variable",
            "price": 4500,
        },
    )
    product_id = product.json()["id"]
    slug = product.json()["slug"]

    attrs = {}
    for attr_name, values in (("Colour", ["Black", "Tan"]), ("Hardware", ["Silver"])):
        created = await client.post(
            "/api/v1/admin/attributes", headers=admin_headers, json={"name": attr_name}
        )
        attr_id = created.json()["id"]
        term_ids = []
        for value in values:
            term = await client.post(
                f"/api/v1/admin/attributes/{attr_id}/terms",
                headers=admin_headers,
                json={"value": value},
            )
            term_ids.append(term.json()["id"])
        attrs[attr_name] = {"id": attr_id, "terms": term_ids}

    await client.put(
        f"/api/v1/admin/products/{product_id}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {"attributeId": attrs["Colour"]["id"], "termIds": attrs["Colour"]["terms"]},
                {"attributeId": attrs["Hardware"]["id"], "termIds": attrs["Hardware"]["terms"]},
            ]
        },
    )
    return {"product_id": product_id, "slug": slug, "attrs": attrs}


@pytest.mark.asyncio
async def test_generate_creates_cartesian_product(client, admin_headers, setup):
    response = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    assert response.status_code == 200
    variations = response.json()
    assert len(variations) == 2  # 2 colours x 1 hardware

    combos = {
        tuple(sorted(v["termValue"] for v in var["values"])) for var in variations
    }
    assert combos == {("Black", "Silver"), ("Silver", "Tan")}


@pytest.mark.asyncio
async def test_generate_seeds_price_from_product(client, admin_headers, setup):
    response = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    for var in response.json():
        assert var["price"] == 4500
        assert var["stock"] == 0


@pytest.mark.asyncio
async def test_regenerating_is_non_destructive(client, admin_headers, setup):
    pid = setup["product_id"]
    first = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    target = first.json()[0]

    await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={"variations": [{"id": target["id"], "price": 9999, "stock": 7, "sku": "W-BLK"}]},
    )

    # Add a third colour, then regenerate
    colour = setup["attrs"]["Colour"]
    new_term = await client.post(
        f"/api/v1/admin/attributes/{colour['id']}/terms",
        headers=admin_headers,
        json={"value": "Cognac"},
    )
    await client.put(
        f"/api/v1/admin/products/{pid}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": colour["id"],
                    "termIds": colour["terms"] + [new_term.json()["id"]],
                },
                {
                    "attributeId": setup["attrs"]["Hardware"]["id"],
                    "termIds": setup["attrs"]["Hardware"]["terms"],
                },
            ]
        },
    )
    again = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )

    assert len(again.json()) == 3  # one new combination only
    kept = next(v for v in again.json() if v["id"] == target["id"])
    assert kept["price"] == 9999
    assert kept["stock"] == 7
    assert kept["sku"] == "W-BLK"


@pytest.mark.asyncio
async def test_simple_product_rejects_variations(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Plain Belt", "description": "A belt.", "price": 2000},
    )
    pid = product.json()["id"]

    response = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    assert response.status_code == 422
    assert "simple" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_without_attributes_is_422(client, admin_headers):
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Empty Variable",
            "description": "No attributes yet.",
            "kind": "variable",
            "price": 100,
        },
    )
    response = await client.post(
        f"/api/v1/admin/products/{product.json()['id']}/variations/generate",
        headers=admin_headers,
    )
    assert response.status_code == 422
    assert "used_for_variations" in response.json()["detail"]


@pytest.mark.asyncio
async def test_term_from_wrong_attribute_rejected(client, admin_headers, setup):
    response = await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": setup["attrs"]["Colour"]["id"],
                    "termIds": setup["attrs"]["Hardware"]["terms"],  # wrong parent
                }
            ]
        },
    )
    assert response.status_code == 422
    assert "do not belong" in response.json()["detail"]


@pytest.mark.asyncio
async def test_variation_images_are_scoped(client, admin_headers, setup):
    """A variation's own images stay its own — `ProductImage.variation_id`
    keeps them out of `product.images`, so an edit to the product's gallery
    can never touch or duplicate them.

    The product's own listing card is a separate question. With nothing
    photographed at the product level, the card falls back to a variation's
    photo (see test_card_image_fallback.py) rather than showing a blank
    placeholder — that is `featuredImage`, and it is expected to be
    populated here. What must not happen is the variation's *gallery*
    physically becoming part of the product's own `images` rows.
    """
    pid = setup["product_id"]
    generated = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    var_id = generated.json()[0]["id"]

    response = await client.post(
        f"/api/v1/admin/products/{pid}/variations/{var_id}/images",
        headers=admin_headers,
        json={"url": "https://cdn.test/black.jpg", "alt": "black", "isFeatured": True},
    )
    assert response.status_code == 200
    assert response.json()["featuredImage"]["url"] == "https://cdn.test/black.jpg"

    product = await client.get("/api/v1/products?pageSize=50")
    row = next(p for p in product.json()["items"] if p["id"] == pid)
    assert row["images"] == []
    assert row["featuredImage"]["url"] == "https://cdn.test/black.jpg"


@pytest.mark.asyncio
async def test_deleting_attribute_in_use_is_409(client, admin_headers, setup):
    response = await client.delete(
        f"/api/v1/admin/attributes/{setup['attrs']['Colour']['id']}",
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "used by 1 product(s)" in response.json()["detail"]


@pytest.mark.asyncio
async def test_deleting_term_in_use_is_409(client, admin_headers, setup):
    colour = setup["attrs"]["Colour"]
    await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )

    response = await client.delete(
        f"/api/v1/admin/attributes/{colour['id']}/terms/{colour['terms'][0]}",
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "variation(s)" in response.json()["detail"]


@pytest.mark.asyncio
async def test_bulk_update_rejects_foreign_variation(client, admin_headers, setup):
    response = await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=admin_headers,
        json={
            "variations": [
                {"id": "00000000-0000-0000-0000-000000000000", "price": 1}
            ]
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_variation(client, admin_headers, setup):
    pid = setup["product_id"]
    generated = await client.post(
        f"/api/v1/admin/products/{pid}/variations/generate", headers=admin_headers
    )
    var_id = generated.json()[0]["id"]

    deleted = await client.delete(
        f"/api/v1/admin/products/{pid}/variations/{var_id}", headers=admin_headers
    )
    assert deleted.status_code == 200

    remaining = await client.get(
        f"/api/v1/admin/products/{pid}/variations", headers=admin_headers
    )
    assert var_id not in [v["id"] for v in remaining.json()]


@pytest.mark.asyncio
async def test_variations_require_admin(client, auth_headers, setup):
    response = await client.get(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_public_detail_exposes_attributes_and_variations(
    client, admin_headers, setup
):
    """The storefront needs the variations themselves, not just a price range."""
    await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )

    response = await client.get(f"/api/v1/products/{setup['slug']}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["kind"] == "variable"
    assert {a["attributeName"] for a in body["attributes"]} == {"Colour", "Hardware"}
    assert all(a["usedForVariations"] for a in body["attributes"])

    assert len(body["variations"]) == 2
    for variation in body["variations"]:
        # Every field the cart and the picker depend on
        assert variation["id"]
        assert variation["price"] > 0
        assert {v["attributeName"] for v in variation["values"]} == {
            "Colour",
            "Hardware",
        }


@pytest.mark.asyncio
async def test_public_detail_hides_inactive_variations(client, admin_headers, setup):
    """An inactive variation is not buyable, so it must not be offered."""
    generated = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    target = generated.json()[0]["id"]

    await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=admin_headers,
        json={"variations": [{"id": target, "isActive": False}]},
    )

    body = (await client.get(f"/api/v1/products/{setup['slug']}")).json()

    assert [v["id"] for v in body["variations"]] == [generated.json()[1]["id"]]


@pytest.mark.asyncio
async def test_simple_product_exposes_attributes_but_no_variations(
    client, admin_headers
):
    """Attributes on a simple product are specifications, not axes."""
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={"name": "Card Holder", "description": "Slim.", "price": 2000},
    )
    product_id = product.json()["id"]

    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Leather"}
    )
    term = await client.post(
        f"/api/v1/admin/attributes/{attr.json()['id']}/terms",
        headers=admin_headers,
        json={"value": "Full grain"},
    )
    await client.put(
        f"/api/v1/admin/products/{product_id}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": attr.json()["id"],
                    "termIds": [term.json()["id"]],
                    "usedForVariations": False,
                }
            ]
        },
    )

    body = (await client.get(f"/api/v1/products/{product.json()['slug']}")).json()
    assert body["kind"] == "simple"
    assert len(body["attributes"]) == 1
    assert body["attributes"][0]["usedForVariations"] is False
    assert body["variations"] == []


@pytest.mark.asyncio
async def test_cannot_demote_attribute_that_variations_depend_on(
    client, admin_headers, setup
):
    """Demoting a live axis would leave variations with no way to pick them."""
    await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )

    response = await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": setup["attrs"]["Colour"]["id"],
                    "termIds": setup["attrs"]["Colour"]["terms"],
                    "usedForVariations": False,
                },
                {
                    "attributeId": setup["attrs"]["Hardware"]["id"],
                    "termIds": setup["attrs"]["Hardware"]["terms"],
                },
            ]
        },
    )
    assert response.status_code == 422
    assert "variation axis" in response.json()["detail"]


@pytest.mark.asyncio
async def test_clearing_every_attribute_detaches_them(client, admin_headers, setup):
    """Sending an empty list is how the admin detaches the last attribute.

    It used to 500: the empty-list guard passed "" to a UUID column, so the
    only way to remove an attribute crashed.
    """
    response = await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/attributes",
        headers=admin_headers,
        json={"attributes": []},
    )
    assert response.status_code == 200, response.text
    assert response.json() == []

    remaining = await client.get(
        f"/api/v1/admin/products/{setup['product_id']}/attributes",
        headers=admin_headers,
    )
    assert remaining.json() == []


@pytest.mark.asyncio
async def test_generated_variations_get_readable_skus(client, admin_headers, setup):
    """A blank SKU column is work the admin has to do by hand for every row."""
    response = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text

    skus = {v["sku"] for v in response.json()}
    assert None not in skus
    assert len(skus) == 2

    # Product stem plus every term slug. Axis order decides the sequence, so
    # the parts are asserted rather than one particular arrangement.
    for variation in response.json():
        sku = variation["sku"]
        assert sku.startswith("BIFOLD-WALLET-")
        for value in variation["values"]:
            assert value["termSlug"].upper() in sku


@pytest.mark.asyncio
async def test_regenerating_does_not_touch_existing_skus(client, admin_headers, setup):
    """Generation is additive — an edited SKU must survive a regenerate."""
    generated = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    target = generated.json()[0]["id"]

    await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=admin_headers,
        json={"variations": [{"id": target, "sku": "HAND-PICKED-001"}]},
    )

    again = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    kept = next(v for v in again.json() if v["id"] == target)
    assert kept["sku"] == "HAND-PICKED-001"


@pytest.mark.asyncio
async def test_variation_skus_are_globally_unique(client, admin_headers, setup):
    """The column is unique across products, so two products sharing a name
    must not generate the same code."""
    first = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    first_skus = {v["sku"] for v in first.json()}

    twin = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Bifold Wallet",
            "description": "A second one.",
            "kind": "variable",
            "price": 4500,
        },
    )
    twin_id = twin.json()["id"]
    await client.put(
        f"/api/v1/admin/products/{twin_id}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": setup["attrs"]["Colour"]["id"],
                    "termIds": setup["attrs"]["Colour"]["terms"],
                }
            ]
        },
    )
    second = await client.post(
        f"/api/v1/admin/products/{twin_id}/variations/generate",
        headers=admin_headers,
    )
    assert second.status_code == 200, second.text

    second_skus = {v["sku"] for v in second.json()}
    assert first_skus.isdisjoint(second_skus)


@pytest.mark.asyncio
async def test_generate_backfills_missing_skus(client, admin_headers, setup):
    """Variations made before SKUs were generated have a blank column.

    Filling a blank is not overwriting a value the admin chose, so generation
    repairs them rather than leaving rows to be typed in by hand.
    """
    generated = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    target = generated.json()[0]["id"]

    # Clear one, as older rows are
    await client.put(
        f"/api/v1/admin/products/{setup['product_id']}/variations",
        headers=admin_headers,
        json={"variations": [{"id": target, "sku": None}]},
    )

    again = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    repaired = next(v for v in again.json() if v["id"] == target)
    assert repaired["sku"], "blank SKU should have been backfilled"
    assert repaired["sku"].startswith("BIFOLD-WALLET-")


@pytest.mark.asyncio
async def test_generated_variation_order_matches_term_position(
    client, admin_headers, setup
):
    """The term order within an axis must come from `AttributeTerm.position`,
    not from however SQLite happens to return an unordered join.

    Regression: `pa.terms` had no `order_by`, so which colour ended up first
    was undefined — observed to flip between Black and Tan depending on what
    else had run in the same test session. Variation position order is what
    the storefront card falls back to when a product has no photo of its own,
    so nondeterminism here silently changes which colour represents a product.
    """
    response = await client.post(
        f"/api/v1/admin/products/{setup['product_id']}/variations/generate",
        headers=admin_headers,
    )
    variations = response.json()

    # setup() creates Colour(Black, Tan) — Black first — and Hardware(Silver)
    def colour_of(variation):
        return next(
            v["termValue"] for v in variation["values"] if v["attributeSlug"] == "colour"
        )

    colours = [colour_of(v) for v in variations]
    assert colours[0] == "Black"
    assert colours[1] == "Tan"


@pytest.mark.asyncio
async def test_reordering_variations_reorders_the_attribute_terms(
    client, admin_headers, setup
):
    """Swatch order and the storefront's default-selected colour both come
    from `attribute.terms` order (see variation-helpers.ts on the storefront),
    which in turn has to follow variation position — reordering variation
    rows in the dashboard is the one lever an admin has to say "Tan is the
    primary colour for this product, not Black"."""
    pid = setup["product_id"]
    generated = (
        await client.post(
            f"/api/v1/admin/products/{pid}/variations/generate",
            headers=admin_headers,
        )
    ).json()

    def colour_of(variation):
        return next(
            v["termValue"] for v in variation["values"] if v["attributeSlug"] == "colour"
        )

    black = next(v for v in generated if colour_of(v) == "Black")
    tan = next(v for v in generated if colour_of(v) == "Tan")
    assert black["position"] < tan["position"]

    before = await client.get(
        f"/api/v1/admin/products/{pid}/attributes", headers=admin_headers
    )
    colour_axis = next(a for a in before.json() if a["attributeSlug"] == "colour")
    assert [t["termValue"] for t in colour_axis["terms"]] == ["Black", "Tan"]

    # Swap positions — Tan should now lead.
    swap = await client.put(
        f"/api/v1/admin/products/{pid}/variations",
        headers=admin_headers,
        json={
            "variations": [
                {"id": black["id"], "position": tan["position"]},
                {"id": tan["id"], "position": black["position"]},
            ]
        },
    )
    assert swap.status_code == 200, swap.text

    after = await client.get(
        f"/api/v1/admin/products/{pid}/attributes", headers=admin_headers
    )
    colour_axis_after = next(a for a in after.json() if a["attributeSlug"] == "colour")
    assert [t["termValue"] for t in colour_axis_after["terms"]] == ["Tan", "Black"]


@pytest.mark.asyncio
async def test_reordering_variations_reorders_the_card_swatch_dots(
    client, admin_headers
):
    """`load_swatches` is a separate, batched query from `get_product_attributes`
    (a product-grid page can't afford one query per card) — same fix, but it
    has its own JOIN and needed its own regression test."""
    product = await client.post(
        "/api/v1/admin/products",
        headers=admin_headers,
        json={
            "name": "Card Holder",
            "description": "A card holder.",
            "kind": "variable",
            "price": 1500,
        },
    )
    product_id = product.json()["id"]

    attr = await client.post(
        "/api/v1/admin/attributes", headers=admin_headers, json={"name": "Colour"}
    )
    attr_id = attr.json()["id"]
    blue = await client.post(
        f"/api/v1/admin/attributes/{attr_id}/terms",
        headers=admin_headers,
        json={"value": "Blue", "meta": {"hex": "#0000FF"}},
    )
    tan = await client.post(
        f"/api/v1/admin/attributes/{attr_id}/terms",
        headers=admin_headers,
        json={"value": "Tan", "meta": {"hex": "#D2B48C"}},
    )

    await client.put(
        f"/api/v1/admin/products/{product_id}/attributes",
        headers=admin_headers,
        json={
            "attributes": [
                {
                    "attributeId": attr_id,
                    "termIds": [blue.json()["id"], tan.json()["id"]],
                }
            ]
        },
    )
    generated = (
        await client.post(
            f"/api/v1/admin/products/{product_id}/variations/generate",
            headers=admin_headers,
        )
    ).json()

    def colour_of(v):
        return v["values"][0]["termValue"]

    blue_var = next(v for v in generated if colour_of(v) == "Blue")
    tan_var = next(v for v in generated if colour_of(v) == "Tan")
    assert blue_var["position"] < tan_var["position"]

    before = await client.get(f"/api/v1/products?ids={product_id}")
    assert [
        s["value"] for s in before.json()["items"][0]["swatches"]
    ] == ["Blue", "Tan"]

    await client.put(
        f"/api/v1/admin/products/{product_id}/variations",
        headers=admin_headers,
        json={
            "variations": [
                {"id": blue_var["id"], "position": tan_var["position"]},
                {"id": tan_var["id"], "position": blue_var["position"]},
            ]
        },
    )

    after = await client.get(f"/api/v1/products?ids={product_id}")
    assert [
        s["value"] for s in after.json()["items"][0]["swatches"]
    ] == ["Tan", "Blue"]
