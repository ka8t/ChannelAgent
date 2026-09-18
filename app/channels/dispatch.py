"""Shared event pipeline every channel adapter calls (#17): authorize,
run the graph, deliver the reply. The one place that connects the Auth
Node and app/graph.py to a NormalizedEvent's reply() callback, so
neither has to know which channel a message came from.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.schema import NormalizedEvent
from app.graph import run_turn
from app.security.auth import authorize

logger = logging.getLogger("channelagent")

DENIED_MESSAGE = "You're not authorized to use this bot yet. Contact an admin to request access."


async def dispatch_event(session: AsyncSession, event: NormalizedEvent) -> None:
    decision = await authorize(session, event.channel, event.user_id)
    if not decision.allowed:
        logger.info("Denied %s/%s: not authorized", event.channel.value, event.user_id)
        await event.reply(DENIED_MESSAGE)
        return

    reply_text = await run_turn(event.channel, event.user_id, event.text)
    await event.reply(reply_text)
