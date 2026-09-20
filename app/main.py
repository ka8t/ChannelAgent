"""ChannelAgent entrypoint.

Currently brings up configuration and the database, which is enough to
prove the application boots correctly inside the container (fails fast
on a missing ENCRYPTION_KEY, creates DB tables on first run). Channel
adapters (Telegram/Email/Matrix — see epic #6 on the issue tracker)
will be wired in here once they exist; there is nothing to route
messages through yet.
"""

import asyncio
import logging

from app.api.deps import MIN_API_KEY_LENGTH, api_key_is_acceptable
from app.config import get_settings
from app.db.bootstrap import bootstrap_admin_from_env
from app.db.session import init_db, session_scope

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("channelagent")


async def main() -> None:
    settings = get_settings()
    await init_db()
    async with session_scope() as session:
        await bootstrap_admin_from_env(session)
    logger.info("ChannelAgent started. LLM gateway: %s", settings.llama_server_url)

    tasks = []
    if settings.telegram_bot_token:
        from app.channels.telegram import run_telegram_adapter

        tasks.append(asyncio.create_task(run_telegram_adapter()))
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram adapter disabled.")

    if settings.email_imap_host and settings.email_username and settings.email_password:
        from app.channels.email import run_email_adapter

        tasks.append(asyncio.create_task(run_email_adapter()))
    else:
        logger.info("Email IMAP/SMTP settings not fully set — Email adapter disabled.")

    # Matrix adapter (#29) joins `tasks` here once it exists.

    if not settings.api_server_key:
        logger.info("API_SERVER_KEY not set — Admin API disabled.")
    elif not api_key_is_acceptable(settings.api_server_key):
        logger.error(
            "API_SERVER_KEY is shorter than %s characters — Admin API NOT started. "
            "Generate a long random key, for example: openssl rand -hex 32",
            MIN_API_KEY_LENGTH,
        )
    else:
        import uvicorn

        from app.api.app import app as admin_api_app

        config = uvicorn.Config(
            admin_api_app,
            host=settings.api_server_host,
            port=settings.api_server_port,
            log_level="info",
        )
        tasks.append(asyncio.create_task(uvicorn.Server(config).serve()))
        logger.info(
            "Admin API starting on %s:%s.", settings.api_server_host, settings.api_server_port
        )

    if not tasks:
        logger.info("No channel adapters are enabled (see epic #6 on the issue tracker).")
        while True:
            await asyncio.sleep(3600)
    else:
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
