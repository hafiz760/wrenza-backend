from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.core.config import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown application resources."""
    settings = get_settings()

    # Setup Redis
    app.state.redis = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    logger.info("Redis connected", url=settings.REDIS_URL)

    # Setup Sentry
    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
        logger.info("Sentry initialized")

    # Background job queue. Emails are sent from the worker, not the request,
    # so a slow SMTP handshake never delays a checkout response.
    from app.tasks.queue import close_queue, init_queue

    if await init_queue():
        logger.info("Task queue connected")

    base_url = f"http://{settings.HOST}:{settings.PORT}"
    print(f"\n  Wrenza API   {base_url}")
    print(f"  Swagger UI   {base_url}/docs")
    print(f"  ReDoc        {base_url}/redoc")
    print(f"  Health       {base_url}/ping\n")

    yield

    # Cleanup
    await close_queue()
    await app.state.redis.close()
    logger.info("Redis connection closed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Wrenza API",
        description="Backend API for Wrenza — Pakistani Wallet Brand",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    )

    # Rate limiting (Redis-backed for multi-worker consistency). The limiter
    # itself lives in app.core.limiter so routers can attach per-endpoint
    # limits to it.
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.core.limiter import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- Register Routers ---

    # Public routes
    from app.api.public.products import router as public_products
    from app.api.public.categories import router as public_categories
    from app.api.public.collections import router as public_collections
    from app.api.public.banners import router as public_banners
    from app.api.public.testimonials import router as public_testimonials
    from app.api.public.contact import router as public_contact
    from app.api.public.checkout import router as public_checkout

    app.include_router(public_products, prefix="/api/v1")
    app.include_router(public_categories, prefix="/api/v1")
    app.include_router(public_collections, prefix="/api/v1")
    app.include_router(public_banners, prefix="/api/v1")
    app.include_router(public_testimonials, prefix="/api/v1")
    app.include_router(public_contact, prefix="/api/v1")
    app.include_router(public_checkout, prefix="/api/v1")

    # Auth routes
    from app.api.auth.router import router as auth_router

    app.include_router(auth_router, prefix="/api/v1")

    # Customer routes
    from app.api.customer.orders import router as customer_orders
    from app.api.customer.wishlist import router as customer_wishlist
    from app.api.customer.reviews import router as customer_reviews
    from app.api.customer.addresses import router as customer_addresses

    app.include_router(customer_orders, prefix="/api/v1")
    app.include_router(customer_wishlist, prefix="/api/v1")
    app.include_router(customer_reviews, prefix="/api/v1")
    app.include_router(customer_addresses, prefix="/api/v1")

    # Admin routes
    from app.api.admin.products import router as admin_products
    from app.api.admin.categories import router as admin_categories
    from app.api.admin.collections import router as admin_collections
    from app.api.admin.orders import router as admin_orders
    from app.api.admin.users import router as admin_users
    from app.api.admin.banners import router as admin_banners
    from app.api.admin.discounts import router as admin_discounts
    from app.api.admin.testimonials import router as admin_testimonials
    from app.api.admin.upload import router as admin_upload
    from app.api.admin.analytics import router as admin_analytics
    from app.api.admin.activity_log import router as admin_activity_log
    from app.api.admin.attributes import router as admin_attributes
    from app.api.admin.options import router as admin_options
    from app.api.admin.variations import router as admin_variations
    from app.api.admin.settings import router as admin_settings
    from app.api.admin.faqs import router as admin_faqs
    from app.api.admin.reviews import router as admin_reviews
    from app.api.admin.media import router as admin_media
    from app.api.admin.cache import router as admin_cache

    app.include_router(admin_products, prefix="/api/v1/admin")
    app.include_router(admin_categories, prefix="/api/v1/admin")
    app.include_router(admin_collections, prefix="/api/v1/admin")
    app.include_router(admin_orders, prefix="/api/v1/admin")
    app.include_router(admin_users, prefix="/api/v1/admin")
    app.include_router(admin_banners, prefix="/api/v1/admin")
    app.include_router(admin_discounts, prefix="/api/v1/admin")
    app.include_router(admin_testimonials, prefix="/api/v1/admin")
    app.include_router(admin_upload, prefix="/api/v1/admin")
    app.include_router(admin_analytics, prefix="/api/v1/admin")
    app.include_router(admin_activity_log, prefix="/api/v1/admin")
    app.include_router(admin_attributes, prefix="/api/v1/admin")
    app.include_router(admin_options, prefix="/api/v1/admin")
    app.include_router(admin_variations, prefix="/api/v1/admin")
    app.include_router(admin_settings, prefix="/api/v1/admin")
    app.include_router(admin_faqs, prefix="/api/v1/admin")
    app.include_router(admin_reviews, prefix="/api/v1/admin")
    app.include_router(admin_media, prefix="/api/v1/admin")
    app.include_router(admin_cache, prefix="/api/v1/admin")

    # ── Global exception handlers ──────────────────────────────

    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import DBAPIError, IntegrityError

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        messages = []
        for err in errors:
            field = " → ".join(str(loc) for loc in err["loc"] if loc != "body")
            msg = err["msg"].removeprefix("Value error, ")
            messages.append(f"{field}: {msg}" if field else msg)
        combined = "; ".join(messages)
        return JSONResponse(
            status_code=422,
            content={"detail": combined},
        )

    @app.exception_handler(DBAPIError)
    async def db_error_handler(request: Request, exc: DBAPIError):
        logger.error("Database error", path=request.url.path, error=str(exc.orig))
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid request data. Please check your input and try again."},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        logger.error("Integrity error", path=request.url.path, error=str(exc.orig))
        return JSONResponse(
            status_code=409,
            content={"detail": "This record already exists or conflicts with existing data."},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled error", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong. Please try again later."},
        )

    # Health check
    @app.get("/ping", tags=["Health"])
    async def health_check():
        return {"status": "ok"}

    return app


app = create_app()
