from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks.email_tasks import (
    send_order_confirmation,
    send_order_status_update,
    send_password_reset,
)
from app.tasks.maintenance_tasks import cleanup_expired_discounts, generate_sitemap


def get_redis_settings() -> RedisSettings:
    settings = get_settings()
    # Parse redis URL: redis://host:port/db
    url = settings.REDIS_URL
    if url.startswith("redis://"):
        url = url[8:]
    parts = url.split("/")
    host_port = parts[0]
    database = int(parts[1]) if len(parts) > 1 else 0
    host, port = host_port.split(":") if ":" in host_port else (host_port, 6379)

    return RedisSettings(host=host, port=int(port), database=database)


class WorkerSettings:
    """arq worker configuration."""

    functions = [
        send_order_confirmation,
        send_order_status_update,
        send_password_reset,
    ]

    cron_jobs = [
        cron(generate_sitemap, hour={0, 6, 12, 18}),  # Every 6 hours
        cron(cleanup_expired_discounts, hour=2, minute=0),  # Daily at 2 AM
    ]

    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300  # 5 minutes
