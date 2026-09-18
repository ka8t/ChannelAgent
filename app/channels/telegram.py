"""Telegram channel adapter (#27): receives messages via long polling,
normalizes them, and routes them through the shared dispatch pipeline
(app/channels/dispatch.py). Delivery back to the user is a closure over
bot.send_message — this module is the only place that knows Telegram's
API shape; app/graph.py and app/security/auth.py never see it.
"""

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from app.channels.dispatch import dispatch_event
from app.channels.schema import NormalizedEvent
from app.config import get_settings
from app.db.models import Channel
from app.db.session import session_scope

logger = logging.getLogger("channelagent")


async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None or update.effective_user is None:
        return

    user_id = str(update.effective_user.id)
    text = update.message.text
    chat_id = update.effective_chat.id

    async def reply(response_text: str) -> None:
        await context.bot.send_message(chat_id=chat_id, text=response_text)

    event = NormalizedEvent(user_id=user_id, channel=Channel.TELEGRAM, text=text, reply=reply)
    async with session_scope() as session:
        await dispatch_event(session, event)


def build_application() -> Application:
    token = get_settings().telegram_bot_token
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    application = Application.builder().token(token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
    return application


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
        logger.info("Telegram adapter started (long polling).")
        try:
            await asyncio.Event().wait()  # runs until this task is cancelled
        finally:
            await application.updater.stop()
            await application.stop()
