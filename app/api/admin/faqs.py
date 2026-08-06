from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.db.models.faq import ProductFaq
from app.db.models.product import Product
from app.schemas.common import MessageResponse
from app.schemas.faq import FaqOut, FaqReplace
from app.services import faq_service

router = APIRouter(prefix="/products/{product_id}/faqs", tags=["Admin - FAQs"])


async def _product_or_404(db, product_id: str) -> Product:
    product = await db.scalar(select(Product).where(Product.id == product_id))
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("", response_model=list[FaqOut])
async def list_faqs(product_id: str, db: DbSession, admin: AdminUser):
    await _product_or_404(db, product_id)
    # Same call the public product page makes, so the editor always shows what
    # the storefront renders and the FAQ schema quotes
    return await faq_service.list_for_product(db, product_id)


@router.put("", response_model=list[FaqOut])
async def replace_faqs(
    product_id: str, data: FaqReplace, admin: AdminUser, db: DbSession
):
    """Replace every FAQ on the product.

    Wholesale replacement rather than per-row edits: the admin reorders and
    rewrites these as a set, and one call keeps positions consistent.
    """
    await _product_or_404(db, product_id)

    existing = await db.execute(
        select(ProductFaq).where(ProductFaq.product_id == product_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)
    await db.flush()

    for index, faq in enumerate(data.faqs):
        db.add(
            ProductFaq(
                product_id=product_id,
                question=faq.question,
                answer=faq.answer,
                position=index,
            )
        )

    await db.commit()
    return await list_faqs(product_id, db, admin)


@router.delete("/{faq_id}", response_model=MessageResponse)
async def delete_faq(
    product_id: str, faq_id: str, admin: AdminUser, db: DbSession
):
    faq = await db.scalar(
        select(ProductFaq).where(
            ProductFaq.id == faq_id, ProductFaq.product_id == product_id
        )
    )
    if not faq:
        raise HTTPException(status_code=404, detail="FAQ not found")

    await db.delete(faq)
    await db.commit()
    return MessageResponse(message="FAQ deleted")
