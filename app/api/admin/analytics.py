from fastapi import APIRouter

from app.core.deps import AdminUser, DbSession
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Admin - Analytics"])


@router.get("/sales-summary")
async def sales_summary(db: DbSession, admin: AdminUser):
    return await analytics_service.get_sales_summary(db)


@router.get("/best-sellers")
async def best_sellers(db: DbSession, admin: AdminUser, limit: int = 10):
    return await analytics_service.get_best_sellers(db, limit=limit)


@router.get("/stock-status")
async def stock_status(db: DbSession, admin: AdminUser, threshold: int = 10):
    return await analytics_service.get_stock_alerts(db, threshold=threshold)


@router.get("/customer-metrics")
async def customer_metrics(db: DbSession, admin: AdminUser):
    return await analytics_service.get_customer_metrics(db)
