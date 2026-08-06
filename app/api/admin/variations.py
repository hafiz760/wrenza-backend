from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.schemas.common import MessageResponse
from app.schemas.variation import (
    ProductAttributeOut,
    ProductAttributesUpdate,
    VariationBulkUpdate,
    VariationImageCreate,
    VariationOut,
)
from app.services import variation_service

router = APIRouter(prefix="/products/{product_id}", tags=["Admin - Variations"])


@router.get("/attributes", response_model=list[ProductAttributeOut])
async def get_attributes(product_id: str, db: DbSession, admin: AdminUser):
    return await variation_service.get_product_attributes(db, product_id)


@router.put("/attributes", response_model=list[ProductAttributeOut])
async def set_attributes(
    product_id: str, data: ProductAttributesUpdate, admin: AdminUser, db: DbSession
):
    return await variation_service.set_product_attributes(db, product_id, data)


@router.post("/variations/generate", response_model=list[VariationOut])
async def generate_variations(product_id: str, admin: AdminUser, db: DbSession):
    """Create every missing combination of the variation-axis terms."""
    return await variation_service.generate_variations(db, product_id)


@router.get("/variations", response_model=list[VariationOut])
async def list_variations(product_id: str, db: DbSession, admin: AdminUser):
    return await variation_service.list_variations(db, product_id)


@router.put("/variations", response_model=list[VariationOut])
async def bulk_update_variations(
    product_id: str, data: VariationBulkUpdate, admin: AdminUser, db: DbSession
):
    return await variation_service.bulk_update_variations(db, product_id, data)


@router.delete("/variations/{variation_id}", response_model=MessageResponse)
async def delete_variation(
    product_id: str, variation_id: str, admin: AdminUser, db: DbSession
):
    await variation_service.delete_variation(db, product_id, variation_id)
    return MessageResponse(message="Variation deleted")


@router.post("/variations/{variation_id}/images", response_model=VariationOut)
async def add_variation_image(
    product_id: str,
    variation_id: str,
    data: VariationImageCreate,
    admin: AdminUser,
    db: DbSession,
):
    return await variation_service.add_variation_image(
        db, product_id, variation_id, data
    )


@router.delete(
    "/variations/{variation_id}/images/{image_id}", response_model=MessageResponse
)
async def delete_variation_image(
    product_id: str,
    variation_id: str,
    image_id: str,
    admin: AdminUser,
    db: DbSession,
):
    await variation_service.delete_variation_image(
        db, product_id, variation_id, image_id
    )
    return MessageResponse(message="Image deleted")
