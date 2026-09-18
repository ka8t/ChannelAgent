"""Shared event pipeline every channel adapter calls (#17): authorize,
run the graph, deliver the reply. The one place that connects the Auth
Node and app/graph.py to a NormalizedEvent's reply() callback, so
neither has to know which channel a message came from.

Also the one place that writes ActionLog rows (#38) and creates
AccessRequests for denied identities (#36) — both via app.admin.service,
the shared layer the interactive CLI (#41) and Admin API also use.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.service import record_action, request_access
from app.channels.schema import NormalizedEvent
from app.db.models import Direction
from app.graph import run_turn
from app.security.auth import authorize
from app.security.hashing import channel_identifier_key

logger = logging.getLogger("channelagent")

DENIED_MESSAGE = (
    "You're not authorized to use this bot yet. An admin has been notified of your request."
)


async def dispatch_event(session: AsyncSession, event: NormalizedEvent) -> None:
    decision = await authorize(session, event.channel, event.user_id)

    if not decision.allowed:
        logger.info("Denied %s/%s: not authorized", event.channel.value, event.user_id)
        key = channel_identifier_key(event.channel, event.user_id)
        await request_access(session, event.channel, key, event.text)
        if decision.user is not None:
            await record_action(
                session, user_id=decision.user.id, channel=event.channel,
                direction=Direction.INBOUND, text=event.text,
            )
        await session.commit()
        await event.reply(DENIED_MESSAGE)
        return

    await record_action(
        session, user_id=decision.user.id, channel=event.channel,
        direction=Direction.INBOUND, text=event.text,
    )
    reply_text = await run_turn(event.channel, event.user_id, event.text)
    await record_action(
        session, user_id=decision.user.id, channel=event.channel,
        direction=Direction.OUTBOUND, text=reply_text,
    )
    await session.commit()
    await event.reply(reply_text)
