from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.collection import CollectionCreate, CollectionUpdate
from app.services import collection_service

router = APIRouter(prefix="/collections", tags=["Admin - Collections"])


@router.get("")
async def list_collections(db: DbSession, admin: AdminUser):
    # Not the public listing — that one hides inactive collections, which would
    # make deactivating one a permanent, unreachable state.
    return await collection_service.list_collections_admin(db)


@router.post("")
async def create_collection(data: CollectionCreate, admin: AdminUser, db: DbSession):
    return await collection_service.create_collection(db, data)


@router.put("/{collection_id}")
async def update_collection(
    collection_id: str, data: CollectionUpdate, admin: AdminUser, db: DbSession
):
    return await collection_service.update_collection(db, collection_id, data)


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str, admin: AdminUser, db: DbSession):
    await collection_service.delete_collection(db, collection_id)
    return {"message": "Collection deleted"}
