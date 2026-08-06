from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import AdminUser, DbSession
from app.db.models.user import User
from app.schemas.user import AdminUserUpdate
from app.utils.pagination import paginate
from app.utils.casing import camelize

router = APIRouter(prefix="/users", tags=["Admin - Users"])


@router.get("")
async def list_users(
    db: DbSession,
    admin: AdminUser,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100, alias="pageSize"),
    search: str | None = None,
):
    query = select(User).order_by(desc(User.created_at))

    if search:
        query = query.where(
            User.email.ilike(f"%{search}%")
            | User.first_name.ilike(f"%{search}%")
            | User.last_name.ilike(f"%{search}%")
        )

    result = await paginate(query, page, pageSize, db)
    result["items"] = [
        {
            "id": str(u.id),
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "phone": u.phone,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in result["items"]
    ]
    return camelize(result)


@router.put("/{user_id}")
async def update_user(user_id: str, data: AdminUserUpdate, admin: AdminUser, db: DbSession):
    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)

    return camelize({
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    })
