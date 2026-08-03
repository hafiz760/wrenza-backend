import asyncio

import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _configure_cloudinary():
    settings = get_settings()
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def _upload_sync(contents: bytes, folder: str) -> dict:
    """Synchronous Cloudinary upload — run in a thread pool."""
    _configure_cloudinary()
    return cloudinary.uploader.upload(
        contents,
        folder=f"kurta-kameez/{folder}",
        resource_type="image",
        transformation=[
            {"quality": "auto", "fetch_format": "auto"},
        ],
    )


def _destroy_sync(public_id: str) -> dict:
    """Synchronous Cloudinary destroy — run in a thread pool."""
    _configure_cloudinary()
    return cloudinary.uploader.destroy(public_id)


async def upload_image(file: UploadFile, folder: str = "products") -> dict:
    """Upload an image to Cloudinary and return URL + metadata."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Use JPEG, PNG, WebP, or GIF.",
        )

    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

    result = await asyncio.to_thread(_upload_sync, contents, folder)

    return {
        "url": result["secure_url"],
        "public_id": result["public_id"],
        "width": result.get("width", 0),
        "height": result.get("height", 0),
    }


async def delete_image(public_id: str) -> bool:
    """Delete an image from Cloudinary by public_id."""
    result = await asyncio.to_thread(_destroy_sync, public_id)
    return result.get("result") == "ok"
