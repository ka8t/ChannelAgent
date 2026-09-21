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
import sys
from collections.abc import Coroutine

from app.api.deps import MIN_API_KEY_LENGTH, api_key_is_acceptable
from app.config import get_settings
from app.db.bootstrap import bootstrap_admin_from_env
from app.db.session import init_db, session_scope
from app.graph import close_graph, get_graph
from app.logging_setup import configure_logging
from app.security.permissions import harden_process, warn_about_loose_application_files

configure_logging()
logger = logging.getLogger("channelagent")


async def _supervised(name: str, hint: str, component: Coroutine) -> None:
    """Run one component (an adapter, the Admin API). If it fails it is logged
    once, with what to check, and stays stopped: the others keep running (#83).
    A Telegram token that Telegram rejects used to end the whole process, API
    included. uvicorn ends with SystemExit when it cannot bind its port, which
    is a failure of that component too, so it is caught here. A shutdown
    (CancelledError, KeyboardInterrupt) is not a failure and goes through.
    """
    try:
        await component
    except (Exception, SystemExit):
        logger.error(
            "%s stopped and will stay stopped; the other components keep running. %s",
            name,
            hint,
            exc_info=True,
        )


async def main() -> int:
    harden_process()
    settings = get_settings()
    await init_db()
    async with session_scope() as session:
        await bootstrap_admin_from_env(session)
    await get_graph()  # opens (and creates) the checkpoint database now, not on the first message
    warn_about_loose_application_files()
    logger.info("ChannelAgent started. LLM gateway: %s", settings.llama_server_url)

    tasks = []
    if settings.telegram_bot_token:
        from app.channels.telegram import run_telegram_adapter

        tasks.append(
            asyncio.create_task(
                _supervised(
                    "Telegram adapter",
                    "Check TELEGRAM_BOT_TOKEN (if it was revoked, issue a new one with BotFather "
                    "and run ./start.sh --set TELEGRAM_BOT_TOKEN=...) and the network.",
                    run_telegram_adapter(),
                )
            )
        )
    else:
        logger.info("TELEGRAM_BOT_TOKEN not set — Telegram adapter disabled.")

    if settings.email_imap_host and settings.email_username and settings.email_password:
        from app.channels.email import run_email_adapter

        tasks.append(
            asyncio.create_task(
                _supervised(
                    "Email adapter",
                    "Check EMAIL_IMAP_HOST, EMAIL_USERNAME, EMAIL_PASSWORD and EMAIL_TRIGGER_TAG.",
                    run_email_adapter(),
                )
            )
        )
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
        tasks.append(
            asyncio.create_task(
                _supervised(
                    "Admin API",
                    "Check API_SERVER_PORT (already in use?) and API_SERVER_HOST.",
                    uvicorn.Server(config).serve(),
                )
            )
        )
        logger.info(
            "Admin API starting on %s:%s.", settings.api_server_host, settings.api_server_port
        )

    try:
        if not tasks:
            logger.info("No channel adapters are enabled (see epic #6 on the issue tracker).")
            while True:
                await asyncio.sleep(3600)
        else:
            await asyncio.gather(*tasks)
            # Every component has ended (a failure was logged by _supervised). Ending
            # with 0 would look like a clean stop to a process manager, and the
            # container would sit idle instead of being restarted or flagged.
            logger.error("Every component has stopped (see the errors above): exiting.")
            return 1
    finally:
        await close_graph()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
