from fastapi import APIRouter, Query

from app.core.deps import AdminUser, DbSession
from app.schemas.media import MediaUsageOut
from app.services.media_service import find_url_references

router = APIRouter(prefix="/media", tags=["Admin - Media"])


@router.get("/usage", response_model=MediaUsageOut)
async def media_usage(
    db: DbSession,
    admin: AdminUser,
    url: str = Query(..., description="Image URL to look for"),
):
    """What references an image, so the dashboard can refuse an unsafe rename.

    Renaming on ImageKit changes the URL, and references here are stored URLs.
    An empty `references` list means the file is unused and safe to rename.
    """
    references = await find_url_references(db, url)
    return MediaUsageOut(in_use=bool(references), references=references)
