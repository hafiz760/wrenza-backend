from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession
from app.db.models.contact import ContactSubmission, NewsletterSubscriber
from app.schemas.common import MessageResponse
from app.schemas.contact import ContactForm, NewsletterSubscribe

router = APIRouter(tags=["Contact"])


@router.post("/contact", response_model=MessageResponse)
async def submit_contact(data: ContactForm, db: DbSession):
    submission = ContactSubmission(
        name=data.name,
        email=data.email,
        subject=data.subject,
        message=data.message,
    )
    db.add(submission)
    await db.commit()
    return MessageResponse(message="Thank you for contacting us. We'll get back to you soon.")


@router.post("/newsletter/subscribe", response_model=MessageResponse)
async def subscribe_newsletter(data: NewsletterSubscribe, db: DbSession):
    existing = await db.scalar(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == data.email)
    )
    if existing:
        if not existing.is_active:
            existing.is_active = True
            await db.commit()
        return MessageResponse(message="You're subscribed to our newsletter!")

    subscriber = NewsletterSubscriber(email=data.email)
    db.add(subscriber)
    await db.commit()
    return MessageResponse(message="You're subscribed to our newsletter!")
