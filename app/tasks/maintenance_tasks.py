from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


async def generate_sitemap(ctx: dict):
    """Generate XML sitemap from active products."""
    logger.info("Starting sitemap generation")
    # TODO: Implement
    # 1. Query all active products
    # 2. Build XML sitemap with product URLs
    # 3. Save to static files or upload to CDN
    logger.info("Sitemap generation complete")


async def cleanup_expired_discounts(ctx: dict):
    """Deactivate expired discount codes."""
    logger.info("Starting expired discount cleanup")
    # TODO: Implement
    # 1. Query discounts where expires_at < now and is_active = True
    # 2. Set is_active = False
    logger.info("Expired discount cleanup complete")
