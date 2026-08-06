from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.promotion import Banner, Discount
from app.schemas.promotion import (
    BannerCreate,
    BannerUpdate,
    DiscountCreate,
    DiscountUpdate,
)
from app.utils.casing import camelize


# --- Discounts ---

async def validate_discount(
    db: AsyncSession, code: str, subtotal: float
) -> dict | None:
    """Validate a discount code and return the discount amount if valid."""
    discount = await db.scalar(
        select(Discount).where(Discount.code == code, Discount.is_active.is_(True))
    )

    if not discount:
        return None

    now = datetime.now(timezone.utc)
    if discount.expires_at and discount.expires_at < now:
        return None

    if discount.max_uses > 0 and discount.current_uses >= discount.max_uses:
        return None

    if subtotal < float(discount.min_order_amount):
        return None

    amount = subtotal * (discount.percentage / 100)

    return {
        "code": discount.code,
        "percentage": discount.percentage,
        "amount": round(amount, 2),
    }


async def apply_discount(db: AsyncSession, code: str) -> None:
    """Increment usage count for a discount code."""
    discount = await db.scalar(select(Discount).where(Discount.code == code))
    if discount:
        discount.current_uses += 1


def _discount_to_out(d: Discount) -> dict:
    return camelize({
        "id": str(d.id),
        "code": d.code,
        "percentage": d.percentage,
        "min_order_amount": float(d.min_order_amount),
        "max_uses": d.max_uses,
        "current_uses": d.current_uses,
        "expires_at": d.expires_at.isoformat() if d.expires_at else None,
        "is_active": d.is_active,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    })


async def list_discounts(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Discount).order_by(desc(Discount.created_at)))
    return [_discount_to_out(d) for d in result.scalars().all()]


async def create_discount(db: AsyncSession, data: DiscountCreate) -> dict:
    existing = await db.scalar(select(Discount).where(Discount.code == data.code))
    if existing:
        raise HTTPException(status_code=409, detail="Discount code already exists")

    discount = Discount(
        code=data.code.upper(),
        percentage=data.percentage,
        min_order_amount=data.min_order_amount,
        max_uses=data.max_uses,
        expires_at=data.expires_at,
        is_active=data.is_active,
    )
    db.add(discount)
    await db.commit()
    await db.refresh(discount)
    return _discount_to_out(discount)


async def update_discount(db: AsyncSession, discount_id: str, data: DiscountUpdate) -> dict:
    discount = await db.scalar(select(Discount).where(Discount.id == discount_id))
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "code" and value:
            value = value.upper()
        setattr(discount, key, value)

    await db.commit()
    await db.refresh(discount)
    return _discount_to_out(discount)


async def delete_discount(db: AsyncSession, discount_id: str) -> None:
    discount = await db.scalar(select(Discount).where(Discount.id == discount_id))
    if not discount:
        raise HTTPException(status_code=404, detail="Discount not found")
    await db.delete(discount)
    await db.commit()


# --- Banners ---

def _banner_to_out(b: Banner) -> dict:
    return camelize({
        "id": str(b.id),
        "title": b.title,
        "image_url": b.image_url,
        "video_url": b.video_url,
        # Lets the frontend branch without inspecting the URL
        "media_type": "video" if b.video_url else "image",
        "link": b.link,
        "position": b.position,
        "active_from": b.active_from.isoformat() if b.active_from else None,
        "active_to": b.active_to.isoformat() if b.active_to else None,
        "is_active": b.is_active,
    })


async def list_active_banners(db: AsyncSession) -> list[dict]:
    now = datetime.now(timezone.utc).date()
    result = await db.execute(
        select(Banner)
        .where(
            Banner.is_active.is_(True),
            (Banner.active_from.is_(None)) | (Banner.active_from <= now),
            (Banner.active_to.is_(None)) | (Banner.active_to >= now),
        )
        .order_by(Banner.position)
    )
    return [_banner_to_out(b) for b in result.scalars().all()]


async def list_all_banners(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Banner).order_by(Banner.position))
    return [_banner_to_out(b) for b in result.scalars().all()]


async def create_banner(db: AsyncSession, data: BannerCreate) -> dict:
    banner = Banner(
        title=data.title,
        image_url=data.image_url,
        video_url=data.video_url,
        link=data.link,
        position=data.position,
        active_from=data.active_from,
        active_to=data.active_to,
        is_active=data.is_active,
    )
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return _banner_to_out(banner)


async def update_banner(db: AsyncSession, banner_id: str, data: BannerUpdate) -> dict:
    banner = await db.scalar(select(Banner).where(Banner.id == banner_id))
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(banner, key, value)

    await db.commit()
    await db.refresh(banner)
    return _banner_to_out(banner)


async def delete_banner(db: AsyncSession, banner_id: str) -> None:
    banner = await db.scalar(select(Banner).where(Banner.id == banner_id))
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    await db.delete(banner)
    await db.commit()
