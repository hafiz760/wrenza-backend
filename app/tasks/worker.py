from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.tasks.email_tasks import (
    send_contact_enquiry,
    send_order_cancelled,
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


# arq defaults to the queue name "arq:queue". Two arq applications sharing a
# Redis would take each other's jobs — silently, and only under load. Both the
# worker and the enqueue side must name the same queue.
QUEUE_NAME = "wz:queue"


class WorkerSettings:
    """arq worker configuration."""

    queue_name = QUEUE_NAME

    # Every job the queue can run. A name missing here is silently dropped
    # at enqueue time, so this list and the enqueue calls must stay in step.
    functions = [
        send_order_confirmation,
        send_order_status_update,
        send_order_cancelled,
        send_password_reset,
        send_contact_enquiry,
    ]

    cron_jobs = [
        cron(generate_sitemap, hour={0, 6, 12, 18}),  # Every 6 hours
        cron(cleanup_expired_discounts, hour=2, minute=0),  # Daily at 2 AM
    ]

    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300  # 5 minutes
