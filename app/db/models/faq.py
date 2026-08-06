from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin


class ProductFaq(Base, UUIDMixin):
    """A buyer question answered on the product page.

    Feeds the FAQPage structured data, which is what wins answer boxes, voice
    results and AI citations. Answers are kept short deliberately: engines lift
    one or two sentences, not paragraphs.
    """

    __tablename__ = "product_faqs"

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped["Product"] = relationship(back_populates="faqs")
