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
        "postgresql+asyncpg://postgres:postgres@localhost:5432/kurta_kameez"
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

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

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
