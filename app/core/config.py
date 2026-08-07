from functools import lru_cache
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/wrenza-db"
    )
    DATABASE_SSL: bool = False

    def model_post_init(self, __context) -> None:
        # Normalize common postgres:// URLs to the async driver format
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        parsed = urlparse(url)
        if parsed.query:
            query = parse_qs(parsed.query, keep_blank_values=True)
            sslmode = query.pop("sslmode", None)
            ssl = query.pop("ssl", None)
            query.pop("channel_binding", None)
            ssl_enabled = False
            if sslmode:
                ssl_value = sslmode[0]
                if ssl_value in {"require", "verify-full", "verify-ca"}:
                    ssl_enabled = True
            if ssl:
                ssl_value = ssl[0].lower()
                if ssl_value in {
                    "true",
                    "1",
                    "yes",
                    "require",
                    "verify-full",
                    "verify-ca",
                }:
                    ssl_enabled = True
            new_query = urlencode(query, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))
            object.__setattr__(self, "DATABASE_SSL", ssl_enabled)
        object.__setattr__(self, "DATABASE_URL", url)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Security
    SECRET_KEY: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Short by design: a reset link sits in an inbox, which is exactly where
    # an attacker with mailbox access would look.
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Email (Titan SMTP)
    # Two mailboxes: order@ sends anything about an order so replies land with
    # the order; info@ sends password resets and contact enquiries. Titan meters
    # sending per mailbox, so the split also keeps the two from starving
    # each other.
    SMTP_HOST: str = "smtp.titan.email"
    SMTP_PORT: int = 465
    SMTP_FROM_NAME: str = "Wrenza"

    SMTP_ORDER_USER: str = ""
    SMTP_ORDER_PASSWORD: str = ""

    SMTP_INFO_USER: str = ""
    SMTP_INFO_PASSWORD: str = ""

    # Where new-order alerts go
    ADMIN_EMAIL: str = ""

    # Base for links inside emails — reset links, order links
    FRONTEND_URL: str = "http://localhost:3001"

    # Logo shown at the top of every email. Must be a public https URL —
    # mail clients cannot reach localhost, and Gmail proxies images through
    # its own servers. Left blank, emails fall back to a text wordmark, which
    # is also what recipients see when their client blocks images.
    # Admin panel, for the "open in dashboard" link on new-order alerts
    DASHBOARD_URL: str = "http://localhost:3000"

    EMAIL_LOGO_URL: str = ""
    EMAIL_LOGO_WIDTH: int = 132

    @property
    def email_enabled(self) -> bool:
        """False when credentials are absent, e.g. in tests or a fresh clone.

        Callers check this rather than discovering it as an SMTP error on a
        background job nobody is watching.
        """
        return bool(self.SMTP_ORDER_PASSWORD or self.SMTP_INFO_PASSWORD)

    # Sentry
    SENTRY_DSN: str = ""

    # Server (used only for the startup banner — uvicorn's own flags still win)
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Debug
    DEBUG: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
