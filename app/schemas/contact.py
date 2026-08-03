from typing import Annotated

from pydantic import EmailStr, Field

from app.schemas.common import CamelModel


class ContactForm(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    email: EmailStr
    subject: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    message: Annotated[str, Field(min_length=5, max_length=2000)]


class NewsletterSubscribe(CamelModel):
    email: EmailStr
