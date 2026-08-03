from fastapi import APIRouter

from app.core.deps import DbSession
from app.services import collection_service

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("")
async def list_collections(db: DbSession):
    return await collection_service.list_collections(db)


@router.get("/{slug}")
async def get_collection(slug: str, db: DbSession):
    return await collection_service.get_by_slug(db, slug)
