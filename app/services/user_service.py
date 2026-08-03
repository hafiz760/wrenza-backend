from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import Address, User
from app.schemas.user import AddressCreate, AddressUpdate


def _address_to_out(a: Address) -> dict:
    return {
        "id": str(a.id),
        "label": a.label,
        "street": a.street,
        "city": a.city,
        "state": a.state,
        "postal_code": a.postal_code,
        "country": a.country,
        "is_default": a.is_default,
    }


async def list_addresses(db: AsyncSession, user_id: UUID) -> list[dict]:
    result = await db.execute(
        select(Address).where(Address.user_id == user_id).order_by(Address.is_default.desc())
    )
    return [_address_to_out(a) for a in result.scalars().all()]


async def create_address(db: AsyncSession, user_id: UUID, data: AddressCreate) -> dict:
    # If setting as default, unset other defaults
    if data.is_default:
        await _unset_defaults(db, user_id)

    address = Address(
        user_id=user_id,
        label=data.label,
        street=data.street,
        city=data.city,
        state=data.state,
        postal_code=data.postal_code,
        country=data.country,
        is_default=data.is_default,
    )
    db.add(address)
    await db.commit()
    return _address_to_out(address)


async def update_address(
    db: AsyncSession, user_id: UUID, address_id: str, data: AddressUpdate
) -> dict:
    address = await db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("is_default"):
        await _unset_defaults(db, user_id)

    for key, value in update_data.items():
        setattr(address, key, value)

    await db.commit()
    return _address_to_out(address)


async def delete_address(db: AsyncSession, user_id: UUID, address_id: str) -> None:
    address = await db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user_id)
    )
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    await db.delete(address)
    await db.commit()


async def _unset_defaults(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
    )
