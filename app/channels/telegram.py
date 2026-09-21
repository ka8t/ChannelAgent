"""Telegram channel adapter (#27): receives messages via long polling,
normalizes them, and routes them through the shared dispatch pipeline
(app/channels/dispatch.py). Delivery back to the user is a closure over
bot.send_message — this module is the only place that knows Telegram's
API shape; app/graph.py and app/security/auth.py never see it.
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app import health
from app.channels import notify
from app.channels.dispatch import dispatch_event, handle_agent_command
from app.channels.schema import NormalizedEvent
from app.config import get_settings
from app.db.models import Channel
from app.db.session import session_scope

logger = logging.getLogger("channelagent")


def _event(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> NormalizedEvent:
    chat_id = update.effective_chat.id

    async def reply(response_text: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=response_text)

    return NormalizedEvent(
        user_id=str(update.effective_user.id), channel=Channel.TELEGRAM, text=text, reply=reply
    )


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None or update.effective_user is None:
        return
    event = _event(update, context, update.message.text)
    async with session_scope() as session:
        await dispatch_event(session, event)


async def _on_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/agent lists the sender's agents, /agent <name> switches (#54)."""
    if update.message is None or update.effective_user is None:
        return
    argument = " ".join(context.args or [])
    event = _event(update, context, f"/agent {argument}".strip())
    async with session_scope() as session:
        await handle_agent_command(session, event, argument)


def build_application() -> Application:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
    application.add_handler(CommandHandler("agent", _on_agent))
    return application


LIVENESS_INTERVAL_SECONDS = 60
LIVENESS_MAX_AGE_SECONDS = 300


async def _liveness_loop(bot, interval: float = LIVENESS_INTERVAL_SECONDS) -> None:
    """Proves the path to Telegram works (`getMe`) and tells the healthcheck (#90).
    A failure is only logged: the container turns unhealthy when none succeeds for
    LIVENESS_MAX_AGE_SECONDS.
    """
    while True:
        try:
            await bot.get_me()
            health.mark("telegram")
        except Exception:
            logger.warning("Telegram getMe failed", exc_info=True)
        await asyncio.sleep(interval)


async def run_telegram_adapter() -> None:
    """Runs inside the caller's own asyncio event loop (app/main.py) —
    deliberately not Application.run_polling(), which manages its own
    loop and isn't meant to be awaited alongside other adapters (Email,
    Matrix) in the same process. Runs until cancelled.
    """
    application = build_application()
    async with application:
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        async def send_to_admin(external_id: str, text: str) -> None:
            await application.bot.send_message(chat_id=int(external_id), text=text)

        notify.register_sender(Channel.TELEGRAM, send_to_admin)
        logger.info("Telegram adapter started (long polling).")
        health.register("telegram", LIVENESS_MAX_AGE_SECONDS)
        liveness = asyncio.create_task(_liveness_loop(application.bot))
        try:
            await asyncio.Event().wait()  # runs until this task is cancelled
        finally:
            liveness.cancel()
            health.unregister("telegram")
            notify.unregister_sender(Channel.TELEGRAM)
            await application.updater.stop()
            await application.stop()
