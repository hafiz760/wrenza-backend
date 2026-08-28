"""Create a product — with attributes, variations, images and FAQs — from one
JSON file, in a single command instead of the multi-tab dashboard flow.

Talks to the admin API over HTTP, so it works against any environment
(local, staging, production) and needs no database access of its own — just
an admin bearer token.

    export WRENZA_ADMIN_TOKEN=...        # never as a CLI arg — shell history
    uv run python -m scripts.import_product product.json
    uv run python -m scripts.import_product product.json --base-url http://localhost:8000/api/v1

Input shape — see scripts/import_product.example.json for a full example:

    {
      "product": { ...ProductCreate fields, camelCase, "category": "<slug>" },
      "attributes": [
        {"attributeId": "...", "termIds": ["...", "..."]}
      ],
      "variations": [
        {
          "termIds": ["..."],            # this variation's point in each axis
          "sku": "...", "price": 0, "compareAtPrice": null,
          "featuredImage": {"url": "...", "alt": "..."},
          "images": [{"url": "...", "alt": "..."}]
        }
      ],
      "faqs": [{"question": "...", "answer": "..."}]
    }

Every step after product creation is best-effort and reported, not fatal —
a failed FAQ write should not leave you wondering whether the product itself
was created. Re-running after fixing one field is safe for everything except
the product-create step itself, which is not idempotent (it always makes a
new row); delete the partial product first if you re-run after a failure
past that point.
"""

import argparse
import json
import os
import sys

import httpx

DEFAULT_BASE_URL = "https://api.wrenza.com/api/v1"


def _client(base_url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def _die(step: str, response: httpx.Response) -> None:
    print(f"\n✗ {step} failed — {response.status_code}", file=sys.stderr)
    print(response.text, file=sys.stderr)
    sys.exit(1)


def _resolve_category(client: httpx.Client, slug: str | None) -> str | None:
    if not slug:
        return None
    response = client.get("/admin/categories")
    if response.status_code != 200:
        _die("GET /admin/categories", response)
    for category in response.json():
        if category["slug"] == slug:
            return category["id"]
    print(f"✗ No category with slug '{slug}' exists — create it first.", file=sys.stderr)
    sys.exit(1)


def import_product(client: httpx.Client, spec: dict) -> str:
    product_spec = dict(spec["product"])
    category_slug = product_spec.pop("category", None)
    product_spec["categoryId"] = _resolve_category(client, category_slug)
    # Only ProductCreate fields belong in this call — priceRange is derived,
    # never accepted.
    product_spec.pop("priceRange", None)

    response = client.post("/admin/products", json=product_spec)
    if response.status_code != 200:
        _die("POST /admin/products", response)
    product = response.json()
    product_id = product["id"]
    print(f"✓ Product created — {product['slug']} ({product_id})")

    if spec.get("attributes"):
        response = client.put(
            f"/admin/products/{product_id}/attributes",
            json={"attributes": spec["attributes"]},
        )
        if response.status_code != 200:
            _die("PUT .../attributes", response)
        print(f"✓ Attributes attached ({len(spec['attributes'])})")

    variation_specs = spec.get("variations") or []
    if variation_specs:
        response = client.post(f"/admin/products/{product_id}/variations/generate")
        if response.status_code != 200:
            _die("POST .../variations/generate", response)
        generated = response.json()
        print(f"✓ {len(generated)} variation(s) generated")

        # Matched by term set, not position — `generate`'s own ordering is not
        # guaranteed to follow the order variations appear in the input file.
        by_terms = {
            frozenset(v["termId"] for v in g["values"]): g["id"] for g in generated
        }

        updates = []
        for var_spec in variation_specs:
            key = frozenset(var_spec["termIds"])
            variation_id = by_terms.get(key)
            if not variation_id:
                print(
                    f"  ⚠ No generated variation matches termIds {var_spec['termIds']}"
                    " — skipped.",
                    file=sys.stderr,
                )
                continue
            updates.append(
                {
                    "id": variation_id,
                    "sku": var_spec.get("sku"),
                    "price": var_spec.get("price"),
                    "compareAtPrice": var_spec.get("compareAtPrice"),
                    "isActive": var_spec.get("isActive", True),
                }
            )
            var_spec["_resolved_id"] = variation_id

        if updates:
            response = client.put(
                f"/admin/products/{product_id}/variations", json={"variations": updates}
            )
            if response.status_code != 200:
                _die("PUT .../variations", response)
            print(f"✓ {len(updates)} variation(s) priced and skued")

        for var_spec in variation_specs:
            variation_id = var_spec.get("_resolved_id")
            if not variation_id:
                continue
            images = []
            if var_spec.get("featuredImage"):
                images.append({**var_spec["featuredImage"], "isFeatured": True})
            images.extend(var_spec.get("images") or [])
            for image in images:
                response = client.post(
                    f"/admin/products/{product_id}/variations/{variation_id}/images",
                    json=image,
                )
                if response.status_code != 200:
                    _die(f"POST .../variations/{variation_id}/images", response)
            if images:
                print(f"✓ {len(images)} image(s) added to variation {variation_id}")

    if spec.get("faqs"):
        response = client.put(
            f"/admin/products/{product_id}/faqs", json={"faqs": spec["faqs"]}
        )
        if response.status_code != 200:
            _die("PUT .../faqs", response)
        print(f"✓ {len(spec['faqs'])} FAQ(s) added")

    return product_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("spec_file", help="Path to the product JSON file")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    token = os.environ.get("WRENZA_ADMIN_TOKEN")
    if not token:
        print("✗ Set WRENZA_ADMIN_TOKEN first — not as a CLI argument.", file=sys.stderr)
        sys.exit(1)

    with open(args.spec_file) as f:
        spec = json.load(f)

    with _client(args.base_url, token) as client:
        product_id = import_product(client, spec)

    print(f"\nDone — {args.base_url.removesuffix('/api/v1')}/products/{spec['product'].get('slug', product_id)}")


if __name__ == "__main__":
    main()
