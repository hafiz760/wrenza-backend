"""Enqueuing background jobs.

The worker in `app.tasks.worker` was configured but nothing ever talked to it —
no pool was created and no service enqueued anything. This is that missing half.
"""

import structlog
from arq import create_pool
from arq.connections import ArqRedis

from app.tasks.worker import QUEUE_NAME, get_redis_settings

logger = structlog.get_logger()

# One pool for the process, created at startup. Opening a connection per job
# would cost a round-trip on the request path.
_pool: ArqRedis | None = None


async def init_queue() -> ArqRedis | None:
    """Open the queue connection. Called once from the app lifespan."""
    global _pool
    try:
        _pool = await create_pool(
            get_redis_settings(), default_queue_name=QUEUE_NAME
        )
    except Exception as exc:
        # A queue that will not connect is worth knowing about, but it must not
        # stop the API from serving — reads and checkout still work without it.
        logger.error("Task queue unavailable", error=str(exc))
        _pool = None
    return _pool


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue(job: str, *args, **kwargs) -> bool:
    """Queue a background job. Returns whether it was accepted.

    Never raises. Callers are in the middle of something that matters more —
    an order being placed, a password being reset — and a queue hiccup must not
    take that down with it. Failures are logged with the arguments, so a
    dropped email can be traced and resent.
    """
    if _pool is None:
        logger.warning("Job not queued — no queue connection", job=job, args=args)
        return False

    try:
        await _pool.enqueue_job(job, *args, **kwargs)
    except Exception as exc:
        logger.error("Job failed to queue", job=job, args=args, error=str(exc))
        return False

    logger.info("Job queued", job=job)
    return True
