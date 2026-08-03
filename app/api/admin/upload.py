from fastapi import APIRouter, UploadFile

from app.core.deps import AdminUser
from app.services import upload_service

router = APIRouter(prefix="/upload", tags=["Admin - Upload"])


@router.post("")
async def upload_image(file: UploadFile, admin: AdminUser, folder: str = "products"):
    return await upload_service.upload_image(file, folder=folder)
