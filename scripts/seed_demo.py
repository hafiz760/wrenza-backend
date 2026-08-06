"""Seed a full demo catalogue so the admin dashboard has real data to render.

Idempotent: every entity is looked up by its natural key first, so running this
twice does not duplicate anything. Pass --wipe to clear demo data first.

    PYTHONPATH=. uv run python scripts/seed_demo.py
    PYTHONPATH=. uv run python scripts/seed_demo.py --wipe
"""

import argparse
import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from itertools import product as cartesian

from sqlalchemy import delete, select

from app.db.models.attribute import Attribute, AttributeTerm
from app.db.models.contact import ContactSubmission, NewsletterSubscriber
from app.db.models.order import Order, OrderItem
from app.db.models.product import Category, Collection, Product, ProductImage
from app.db.models.promotion import Banner, Discount
from app.db.models.review import Testimonial
from app.db.models.user import User, UserRole
from app.db.models.variation import (
    ProductAttribute,
    ProductAttributeTerm,
    ProductVariation,
    VariationAttributeValue,
)
from app.db.session import AsyncSessionLocal
from app.core.security import hash_password_sync
from app.utils.slug import generate_slug

IK = "https://ik.imagekit.io/wrenza"


def img(name: str) -> str:
    return f"{IK}/demo/{name}.jpg"


CATEGORIES = [
    ("Wallets", "Slim bifolds, trifolds and card holders in full grain leather."),
    ("Bags", "Weekenders, totes and messenger bags built to outlast trends."),
    ("Belts", "Hand-finished belts with solid brass and steel hardware."),
    ("Accessories", "Key holders, cable rolls and the small things that matter."),
]

SUBCATEGORIES = {
    "Wallets": ["Bifold", "Card Holder"],
    "Bags": ["Weekender", "Messenger"],
}

ATTRIBUTES = [
    ("Leather Colour", True, [
        ("Black", "#111111"), ("Tan", "#B4713D"),
        ("Cognac", "#8C4A2F"), ("Oxblood", "#5C1F1F"),
    ]),
    ("Hardware Finish", True, [
        ("Brass", "#C6A15B"), ("Gunmetal", "#4A4E54"), ("Nickel", "#D6D6D6"),
    ]),
    ("Belt Size", True, [
        ("30", None), ("32", None), ("34", None), ("36", None), ("38", None),
    ]),
]

# (name, category, type, price, kind, variation attributes, featured, new)
PRODUCTS = [
    ("Heritage Bifold Wallet", "Wallets", "wallet", 6500, "variable",
     ["Leather Colour", "Hardware Finish"], True, True),
    ("Slim Card Holder", "Wallets", "card-holder", 3200, "variable",
     ["Leather Colour"], True, False),
    ("Traveller Trifold", "Wallets", "wallet", 7800, "simple", [], False, True),
    ("Weekender Duffle", "Bags", "bag", 24500, "variable",
     ["Leather Colour", "Hardware Finish"], True, False),
    ("Field Messenger", "Bags", "bag", 18900, "variable",
     ["Leather Colour"], False, True),
    ("Everyday Tote", "Bags", "bag", 15600, "simple", [], False, False),
    ("Classic Dress Belt", "Belts", "belt", 4900, "variable",
     ["Belt Size", "Leather Colour"], True, False),
    ("Woven Casual Belt", "Belts", "belt", 4200, "simple", [], False, True),
    ("Leather Key Holder", "Accessories", "accessory", 1800, "simple", [], False, False),
    ("Cable Roll", "Accessories", "accessory", 2400, "simple", [], False, True),
    ("Passport Sleeve", "Accessories", "accessory", 3900, "simple", [], True, False),
    ("Coin Pouch", "Accessories", "accessory", 1500, "simple", [], False, False),
]

TESTIMONIALS = [
    ("Ayesha Khan", "Lahore", "The stitching is flawless. Two years in and it looks better than new.", 5),
    ("Bilal Ahmed", "Karachi", "Ordered the weekender for a work trip — it drew compliments at every stop.", 5),
    ("Sana Mirza", "Islamabad", "Delivery took a little longer than expected, but the wallet is superb.", 4),
    ("Usman Tariq", "Rawalpindi", "Finally a belt that does not crack after six months.", 5),
    ("Hina Farooq", "Multan", "The cognac leather is even richer in person.", 5),
]

BANNERS = [
    ("Autumn Leather Edit", "banner-autumn", "/collections/autumn", 0, None),
    ("The Weekender Film", "banner-weekender", "/products/weekender-duffle", 1,
     f"{IK}/demo/weekender.mov/ik-video.mp4"),
    ("Free Shipping Over PKR 5000", "banner-shipping", None, 2, None),
]

DISCOUNTS = [
    ("WELCOME10", 10, 0, 500, 42),
    ("AUTUMN20", 20, 5000, 200, 118),
    ("VIP25", 25, 10000, 50, 7),
    ("EXPIRED15", 15, 0, 100, 100),
]

CUSTOMERS = [
    ("Ayesha", "Khan", "ayesha.khan@example.com"),
    ("Bilal", "Ahmed", "bilal.ahmed@example.com"),
    ("Sana", "Mirza", "sana.mirza@example.com"),
    ("Usman", "Tariq", "usman.tariq@example.com"),
    ("Hina", "Farooq", "hina.farooq@example.com"),
]

ORDER_STATUSES = [
    "pending", "confirmed", "processing", "shipped", "delivered", "cancelled"
]


async def _wipe(db) -> None:
    """Clear demo data. Order matters — children before parents."""
    for model in (
        OrderItem, Order, VariationAttributeValue, ProductVariation,
        ProductAttributeTerm, ProductAttribute, ProductImage, Product,
        AttributeTerm, Attribute, Collection, Category, Banner, Discount,
        Testimonial, ContactSubmission, NewsletterSubscriber,
    ):
        await db.execute(delete(model))
    await db.execute(delete(User).where(User.role == UserRole.CUSTOMER))
    await db.commit()
    print("  wiped existing demo data")


async def _get_or_create(db, model, defaults=None, **lookup):
    existing = await db.scalar(select(model).filter_by(**lookup))
    if existing:
        return existing, False
    obj = model(**lookup, **(defaults or {}))
    db.add(obj)
    await db.flush()
    return obj, True


async def seed() -> None:
    parser = argparse.ArgumentParser(description="Seed demo catalogue data")
    parser.add_argument("--wipe", action="store_true", help="clear demo data first")
    args = parser.parse_args()

    random.seed(7)  # stable output across runs

    async with AsyncSessionLocal() as db:
        if args.wipe:
            await _wipe(db)

        # ── Categories ──
        categories: dict[str, Category] = {}
        for name, description in CATEGORIES:
            cat, _ = await _get_or_create(
                db, Category, slug=generate_slug(name),
                defaults={"name": name, "description": description,
                          "image_url": img(generate_slug(name)), "is_active": True},
            )
            categories[name] = cat

        for parent_name, children in SUBCATEGORIES.items():
            for child in children:
                await _get_or_create(
                    db, Category, slug=generate_slug(f"{parent_name} {child}"),
                    defaults={"name": child, "parent_id": categories[parent_name].id,
                              "is_active": True},
                )
        await db.commit()
        print(f"  categories: {len(categories)} top-level + subcategories")

        # ── Attributes and terms ──
        attributes: dict[str, Attribute] = {}
        terms: dict[str, list[AttributeTerm]] = {}
        for name, filterable, values in ATTRIBUTES:
            attr, _ = await _get_or_create(
                db, Attribute, slug=generate_slug(name),
                defaults={"name": name, "is_filterable": filterable},
            )
            attributes[name] = attr
            terms[name] = []
            for position, (value, hex_code) in enumerate(values):
                term, _ = await _get_or_create(
                    db, AttributeTerm, attribute_id=attr.id, slug=generate_slug(value),
                    defaults={"value": value, "position": position,
                              "meta": {"hex": hex_code} if hex_code else {}},
                )
                terms[name].append(term)
        await db.commit()
        print(f"  attributes: {len(attributes)} with "
              f"{sum(len(v) for v in terms.values())} terms")

        # ── Products ──
        created_products: list[Product] = []
        variation_count = 0
        for name, cat_name, ptype, price, kind, axes, featured, new in PRODUCTS:
            slug = generate_slug(name)
            product, is_new = await _get_or_create(
                db, Product, slug=slug,
                defaults={
                    "name": name,
                    "description": (
                        f"{name} — cut from full grain leather and finished by hand. "
                        "Ages into a patina unique to how you carry it."
                    ),
                    "kind": kind,
                    "price": price,
                    "compare_at_price": round(price * 1.25) if featured else None,
                    "category_id": categories[cat_name].id,
                    "product_type": ptype,
                    "dimensions": {"lengthCm": 11.5, "widthCm": 9.0, "heightCm": 2.0},
                    "care_instructions": [
                        "Wipe with a dry cloth",
                        "Condition every six months",
                        "Keep away from prolonged damp",
                    ],
                    "tags": ["leather", "handmade", ptype],
                    "stock": random.randint(8, 60) if kind == "simple" else 0,
                    "rating": round(random.uniform(4.0, 5.0), 1),
                    "review_count": random.randint(3, 40),
                    "is_featured": featured,
                    "is_new_arrival": new,
                    "is_active": True,
                    "meta_title": f"{name} | Wrenza",
                },
            )
            created_products.append(product)
            if not is_new:
                continue

            # Feature image plus a small gallery
            db.add(ProductImage(
                product_id=product.id, url=img(f"{slug}-hero"),
                alt=f"{name} hero", width=1200, height=1200,
                position=-1, is_featured=True,
            ))
            for i in range(1, 4):
                db.add(ProductImage(
                    product_id=product.id, url=img(f"{slug}-{i}"),
                    alt=f"{name} view {i}", width=1000, height=1000, position=i,
                ))
            await db.flush()

            if kind != "variable":
                continue

            # Attach the variation axes, then generate every combination
            axis_term_ids: list[list[str]] = []
            for position, axis in enumerate(axes):
                pa = ProductAttribute(
                    product_id=product.id, attribute_id=attributes[axis].id,
                    position=position, used_for_variations=True,
                )
                db.add(pa)
                await db.flush()
                for term in terms[axis]:
                    db.add(ProductAttributeTerm(
                        product_attribute_id=pa.id, term_id=term.id
                    ))
                axis_term_ids.append([t.id for t in terms[axis]])

            for index, combo in enumerate(cartesian(*axis_term_ids)):
                variation = ProductVariation(
                    product_id=product.id,
                    sku=f"{slug[:12].upper().replace('-', '')}-{index + 1:03d}",
                    price=price + (index % 3) * 400,
                    stock=random.randint(0, 25),
                    position=index,
                    is_active=True,
                )
                db.add(variation)
                await db.flush()
                for term_id in combo:
                    term = await db.get(AttributeTerm, term_id)
                    db.add(VariationAttributeValue(
                        variation_id=variation.id,
                        attribute_id=term.attribute_id,
                        term_id=term_id,
                    ))
                variation_count += 1

        await db.commit()
        print(f"  products: {len(created_products)} "
              f"({variation_count} variations generated)")

        # ── Collections ──
        featured_ids = [str(p.id) for p in created_products if p.is_featured]
        new_ids = [str(p.id) for p in created_products if p.is_new_arrival]
        for name, tagline, ids, season in (
            ("Autumn Edit", "Warm tones for shorter days", featured_ids, "Autumn"),
            ("Just Landed", "The newest additions to the workshop", new_ids, None),
        ):
            await _get_or_create(
                db, Collection, slug=generate_slug(name),
                defaults={"name": name, "tagline": tagline, "product_ids": ids,
                          "season": season, "year": 2026, "is_featured": True,
                          "image": img(generate_slug(name)), "is_active": True},
            )
        await db.commit()
        print("  collections: 2")

        # ── Banners, discounts, testimonials ──
        for title, image_slug, link, position, video in BANNERS:
            await _get_or_create(
                db, Banner, title=title,
                defaults={"image_url": img(image_slug), "video_url": video,
                          "link": link, "position": position, "is_active": True,
                          "active_from": date.today() - timedelta(days=7)},
            )

        now = datetime.now(timezone.utc)
        for code, pct, min_amount, max_uses, used in DISCOUNTS:
            expired = code == "EXPIRED15"
            await _get_or_create(
                db, Discount, code=code,
                defaults={"percentage": pct, "min_order_amount": min_amount,
                          "max_uses": max_uses, "current_uses": used,
                          "expires_at": now - timedelta(days=3) if expired
                                        else now + timedelta(days=45),
                          "is_active": not expired},
            )

        for name, location, comment, rating in TESTIMONIALS:
            await _get_or_create(
                db, Testimonial, name=name,
                defaults={"location": location, "comment": comment,
                          "rating": rating, "avatar": img(generate_slug(name)),
                          "is_active": True},
            )
        await db.commit()
        print(f"  banners: {len(BANNERS)}, discounts: {len(DISCOUNTS)}, "
              f"testimonials: {len(TESTIMONIALS)}")

        # ── Customers ──
        customers = []
        for first, last, email in CUSTOMERS:
            user, _ = await _get_or_create(
                db, User, email=email,
                defaults={"first_name": first, "last_name": last,
                          "password_hash": hash_password_sync("password123"),
                          "role": UserRole.CUSTOMER, "is_active": True,
                          "phone": f"0300{random.randint(1000000, 9999999)}"},
            )
            customers.append(user)
        await db.commit()
        print(f"  customers: {len(customers)}")

        # ── Orders across every status and the last 60 days ──
        simple_products = [p for p in created_products if p.kind == "simple"]
        order_count = 0
        existing_orders = await db.scalar(select(Order).limit(1))
        if not existing_orders:
            for i in range(24):
                customer = random.choice(customers)
                placed = now - timedelta(days=random.randint(0, 60),
                                         hours=random.randint(0, 23))
                chosen = random.sample(simple_products, k=random.randint(1, 3))

                subtotal = 0.0
                lines = []
                for prod in chosen:
                    qty = random.randint(1, 3)
                    subtotal += float(prod.price) * qty
                    lines.append((prod, qty))

                shipping = 0.0 if subtotal >= 5000 else 250.0
                order = Order(
                    user_id=customer.id,
                    order_number=f"WZ-2026-{i + 1:03d}",
                    status=random.choice(ORDER_STATUSES),
                    subtotal=subtotal,
                    shipping=shipping,
                    discount=0,
                    total=subtotal + shipping,
                    shipping_address={
                        "label": "Home",
                        "street": f"{random.randint(1, 200)} Gulberg Road",
                        "city": random.choice(["Lahore", "Karachi", "Islamabad"]),
                        "state": "Punjab",
                        "postalCode": "54000",
                        "country": "Pakistan",
                    },
                    payment_method="Cash on Delivery",
                    email=customer.email,
                    phone=customer.phone,
                    guest_first_name=customer.first_name,
                    guest_last_name=customer.last_name,
                    created_at=placed,
                    updated_at=placed,
                )
                db.add(order)
                await db.flush()

                for prod, qty in lines:
                    db.add(OrderItem(
                        order_id=order.id,
                        product_id=prod.id,
                        product_snapshot={
                            "id": str(prod.id), "name": prod.name,
                            "slug": prod.slug, "price": float(prod.price),
                            "currency": "PKR",
                        },
                        quantity=qty,
                        unit_price=float(prod.price),
                    ))
                order_count += 1
            await db.commit()
        print(f"  orders: {order_count}")

        # ── Contact + newsletter, so those screens are not empty ──
        for i in range(4):
            await _get_or_create(
                db, ContactSubmission, email=f"enquiry{i + 1}@example.com",
                defaults={"name": f"Enquirer {i + 1}",
                          "subject": "Question about sizing",
                          "message": "Do the belts run true to waist size?",
                          "is_read": i % 2 == 0},
            )
        for i in range(6):
            await _get_or_create(
                db, NewsletterSubscriber, email=f"subscriber{i + 1}@example.com",
                defaults={"is_active": True},
            )
        await db.commit()

        print("\nDone. Log in as admin@wrenza.com to see it.")


if __name__ == "__main__":
    asyncio.run(seed())
