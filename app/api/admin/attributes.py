from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.attribute import (
    AttributeCreate,
    AttributeOut,
    AttributeTermCreate,
    AttributeTermOut,
    AttributeTermUpdate,
    AttributeUpdate,
)
from app.schemas.common import MessageResponse
from app.services import attribute_service

router = APIRouter(prefix="/attributes", tags=["Admin - Attributes"])


@router.get("", response_model=list[AttributeOut])
async def list_attributes(db: DbSession, admin: AdminUser):
    return await attribute_service.list_attributes(db)


@router.post("", response_model=AttributeOut)
async def create_attribute(data: AttributeCreate, admin: AdminUser, db: DbSession):
    return await attribute_service.create_attribute(db, data)


@router.put("/{attribute_id}", response_model=AttributeOut)
async def update_attribute(
    attribute_id: str, data: AttributeUpdate, admin: AdminUser, db: DbSession
):
    return await attribute_service.update_attribute(db, attribute_id, data)


@router.delete("/{attribute_id}", response_model=MessageResponse)
async def delete_attribute(attribute_id: str, admin: AdminUser, db: DbSession):
    await attribute_service.delete_attribute(db, attribute_id)
    return MessageResponse(message="Attribute deleted")


@router.post("/{attribute_id}/terms", response_model=AttributeTermOut)
async def create_term(
    attribute_id: str, data: AttributeTermCreate, admin: AdminUser, db: DbSession
):
    return await attribute_service.create_term(db, attribute_id, data)


@router.put("/{attribute_id}/terms/{term_id}", response_model=AttributeTermOut)
async def update_term(
    attribute_id: str,
    term_id: str,
    data: AttributeTermUpdate,
    admin: AdminUser,
    db: DbSession,
):
    return await attribute_service.update_term(db, attribute_id, term_id, data)


@router.delete("/{attribute_id}/terms/{term_id}", response_model=MessageResponse)
async def delete_term(
    attribute_id: str, term_id: str, admin: AdminUser, db: DbSession
):
    await attribute_service.delete_term(db, attribute_id, term_id)
    return MessageResponse(message="Attribute term deleted")
