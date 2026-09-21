"""Application configuration, loaded from environment variables (.env).

Fails fast on missing required settings instead of falling back to
insecure defaults — a missing ENCRYPTION_KEY must never silently
result in unencrypted storage.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env also carries shell-only variables start.sh
    # reads directly (LLAMA_SERVER_BIN, MODELS_DIR, LLAMA_PORT — used to
    # auto-start a native llama-server, never by this Python process).
    # Without this, adding one of those breaks Settings() with "Extra
    # inputs are not permitted" for a variable the app never touches.
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    # Conversation checkpoints (#49). A separate SQLite file, so Alembic keeps
    # owning only the application's tables and the checkpointer its own.
    # Empty: "checkpoints.db" next to the main SQLite database file.
    checkpoint_db_path: str | None = Field(default=None, alias="CHECKPOINT_DB_PATH")
    # How many pre-migration copies of the database to keep in backups/ next to
    # it (#66). 0 turns the backup off.
    migration_backups_keep: int = Field(default=5, alias="MIGRATION_BACKUPS_KEEP")
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
    # The mailbox is shared with ordinary mail (website contact form,
    # customer questions), so the adapter only touches messages whose
    # subject contains this tag. Empty means "process nothing", never
    # "process everything". See docs/ARCHITECTURE.md ("Email on a shared
    # mailbox").
    email_trigger_tag: str = Field(default="[agent]", alias="EMAIL_TRIGGER_TAG")
    # Where a handled agent message is filed so it leaves the INBOX humans
    # read. Created on first use. The default follows the OVH/Dovecot
    # layout ("." separator under INBOX); change it for another provider.
    # Empty means "leave handled messages in the INBOX".
    email_agent_folder: str = Field(default="INBOX.Agent", alias="EMAIL_AGENT_FOLDER")

    # Matrix adapter (#29, not yet implemented)
    matrix_homeserver_url: str | None = Field(default=None, alias="MATRIX_HOMESERVER_URL")
    matrix_bot_user_id: str | None = Field(default=None, alias="MATRIX_BOT_USER_ID")
    matrix_bot_access_token: str | None = Field(default=None, alias="MATRIX_BOT_ACCESS_TOKEN")

    # Admin API
    api_server_port: int = Field(default=8700, alias="API_SERVER_PORT")
    # Interface the Admin API binds to (#52). Loopback by default: the API
    # serves decrypted conversations behind one static key over plain HTTP,
    # so reaching it from the network must be a deliberate choice. The
    # Docker image sets 0.0.0.0 *inside* the container, where the host-side
    # exposure is decided by docker-compose's published address instead.
    api_server_host: str = Field(default="127.0.0.1", alias="API_SERVER_HOST")
    api_server_key: str | None = Field(default=None, alias="API_SERVER_KEY")
    # Names the API answers to (#108): a request with another Host is refused (421),
    # which stops DNS rebinding from a web page. Add the name of a TLS proxy here.
    # Empty means the loopback names.
    allowed_hosts: str = Field(default="localhost,127.0.0.1,::1", alias="ALLOWED_HOSTS")
    # A request body larger than this is refused (413), a request slower than this
    # is cut (504) (#108).
    api_max_body_bytes: int = Field(default=1_048_576, alias="API_MAX_BODY_BYTES")
    api_request_timeout_seconds: int = Field(default=60, alias="API_REQUEST_TIMEOUT_SECONDS")

    # Model management (#104). The directory of the `.gguf` files (start.sh reads the same
    # variable to start the engine), the hub a model is pulled from, the extra hosts a pull
    # may reach, the size and time limits of one pull, and the token for gated models.
    models_dir: str = Field(default="models", alias="MODELS_DIR")
    model_hub_url: str = Field(default="https://huggingface.co", alias="MODEL_HUB_URL")
    model_pull_allowed_hosts: str = Field(default="", alias="MODEL_PULL_ALLOWED_HOSTS")
    model_pull_max_bytes: int = Field(default=64 * 1024**3, alias="MODEL_PULL_MAX_BYTES")
    model_pull_timeout_seconds: int = Field(default=6 * 3600, alias="MODEL_PULL_TIMEOUT_SECONDS")
    hf_token: str | None = Field(default=None, alias="HF_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
