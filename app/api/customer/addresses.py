from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.user import AddressCreate, AddressOut, AddressUpdate
from app.services import user_service

router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.get("", response_model=list[AddressOut])
async def list_addresses(user: CurrentUser, db: DbSession):
    return await user_service.list_addresses(db, user.id)


@router.post("", response_model=AddressOut)
async def create_address(data: AddressCreate, user: CurrentUser, db: DbSession):
    return await user_service.create_address(db, user.id, data)


@router.put("/{address_id}", response_model=AddressOut)
async def update_address(address_id: str, data: AddressUpdate, user: CurrentUser, db: DbSession):
    return await user_service.update_address(db, user.id, address_id, data)


@router.delete("/{address_id}", response_model=MessageResponse)
async def delete_address(address_id: str, user: CurrentUser, db: DbSession):
    await user_service.delete_address(db, user.id, address_id)
    return MessageResponse(message="Address deleted")
