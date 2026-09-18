"""Application configuration, loaded from environment variables (.env).

Fails fast on missing required settings instead of falling back to
insecure defaults — a missing ENCRYPTION_KEY must never silently
result in unencrypted storage.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Application-layer encryption (see app/security/encryption.py)
    encryption_key: str = Field(..., alias="ENCRYPTION_KEY")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/channelagent.db",
        alias="DATABASE_URL",
    )

    # Local LLM gateway
    llama_server_url: str = Field(
        default="http://host.docker.internal:8080", alias="LLAMA_SERVER_URL"
    )
    llama_ctx_size: int = Field(default=65536, alias="LLAMA_CTX_SIZE")
    model_file: str | None = Field(default=None, alias="MODEL_FILE")

    # Telegram adapter
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    # Bootstrap only (#14) — never consulted by the Auth Node (#12) after
    # the first admin user has been seeded from it.
    telegram_allowed_users: str | None = Field(default=None, alias="TELEGRAM_ALLOWED_USERS")

    # Email adapter
    email_imap_host: str | None = Field(default=None, alias="EMAIL_IMAP_HOST")
    email_imap_port: int = Field(default=993, alias="EMAIL_IMAP_PORT")
    email_smtp_host: str | None = Field(default=None, alias="EMAIL_SMTP_HOST")
    email_smtp_port: int = Field(default=587, alias="EMAIL_SMTP_PORT")
    email_username: str | None = Field(default=None, alias="EMAIL_USERNAME")
    email_password: str | None = Field(default=None, alias="EMAIL_PASSWORD")

    # Matrix adapter
    matrix_homeserver_url: str | None = Field(default=None, alias="MATRIX_HOMESERVER_URL")
    matrix_user_id: str | None = Field(default=None, alias="MATRIX_USER_ID")
    matrix_access_token: str | None = Field(default=None, alias="MATRIX_ACCESS_TOKEN")

    # Admin API
    api_server_port: int = Field(default=8700, alias="API_SERVER_PORT")
    api_server_key: str | None = Field(default=None, alias="API_SERVER_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
