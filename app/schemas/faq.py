from typing import Annotated

# pyrefly: ignore [missing-import]
from pydantic import Field

from app.schemas.common import CamelModel


class FaqOut(CamelModel):
    id: str
    question: str
    answer: str
    position: int


class FaqUpsert(CamelModel):
    """One FAQ row. Answers are capped short on purpose — answer engines lift
    a sentence or two, and long prose does not get quoted."""

    question: Annotated[str, Field(min_length=3, max_length=300)]
    answer: Annotated[str, Field(min_length=3, max_length=1000)]
    position: Annotated[int, Field(ge=0)] = 0


class FaqReplace(CamelModel):
    """Replaces the product's whole FAQ list, so reordering is one call."""

    faqs: list[FaqUpsert] = Field(default_factory=list)
