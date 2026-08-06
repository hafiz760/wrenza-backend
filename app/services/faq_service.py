from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.faq import ProductFaq
from app.schemas.faq import FaqOut


def faq_to_out(faq: ProductFaq) -> FaqOut:
    return FaqOut(
        id=str(faq.id),
        question=faq.question,
        answer=faq.answer,
        position=faq.position,
    )


async def list_for_product(db: AsyncSession, product_id: str) -> list[FaqOut]:
    """A product's FAQs in display order.

    Shared by the admin editor and the public product page: the FAQPage
    structured data must quote exactly what the page shows, so both sides read
    the same rows through the same ordering.
    """
    result = await db.execute(
        select(ProductFaq)
        .where(ProductFaq.product_id == product_id)
        .order_by(ProductFaq.position)
    )
    return [faq_to_out(faq) for faq in result.scalars().all()]
