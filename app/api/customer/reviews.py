from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession, RedisClient
from app.schemas.review import ReviewCreate, ReviewOut
from app.services import review_service

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.post("", response_model=ReviewOut)
async def create_review(data: ReviewCreate, user: CurrentUser, db: DbSession, redis: RedisClient):
    return await review_service.create_review(db, user.id, data, redis=redis)
