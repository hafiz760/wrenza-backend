from fastapi import APIRouter, Request

from app.core.deps import DbSession, OptionalUser, RedisClient
from app.core.limiter import limiter
from app.schemas.review import ReviewCreate, ReviewOut
from app.services import review_service

router = APIRouter(prefix="/reviews", tags=["Reviews"])


# Far below the global 100/minute. This endpoint needs no credentials, so
# the default would let one address post a hundred reviews a minute.
@router.post("", response_model=ReviewOut)
@limiter.limit("5/hour")
async def create_review(
    request: Request,
    data: ReviewCreate,
    user: OptionalUser,
    db: DbSession,
    redis: RedisClient,
):
    """Leave a review, with or without an account.

    Open on purpose — requiring a login or a matching order would mean almost
    no reviews on a young catalogue. Nothing is published on the strength of
    this call: reviews are created pending and an admin approves them.

    `request` is unused by the handler but required by slowapi, which reads the
    client address off it to apply the limit below.
    """
    return await review_service.create_review(db, user, data, redis=redis)
