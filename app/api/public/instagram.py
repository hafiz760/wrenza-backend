from fastapi import APIRouter

from app.core.deps import DbSession, RedisClient
from app.services import instagram_service

router = APIRouter(prefix="/instagram", tags=["Instagram"])


@router.get("/media")
async def list_media(db: DbSession, redis: RedisClient):
    return {"data": await instagram_service.get_media(db, redis)}
