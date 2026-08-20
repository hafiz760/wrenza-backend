"""The shared rate limiter.

Module-level rather than built inside `create_app()` so routers can decorate
individual endpoints with their own limits. The app wires the same instance
into `app.state` at startup.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=settings.REDIS_URL,
    # Without this slowapi writes bare LIMITER/... keys, which another slowapi
    # app on the same Redis would share — and so would its limits.
    key_prefix="wz:ratelimit",
)
