"""Shared event pipeline every channel adapter calls (#17): authorize,
run the graph, deliver the reply. The one place that connects the Auth
Node and app/graph.py to a NormalizedEvent's reply() callback, so
neither has to know which channel a message came from.

Also the one place that writes ActionLog rows (#38) and creates
AccessRequests for denied identities (#36) — both via app.admin.service,
the shared layer the interactive CLI (#41) and Admin API also use.
"""

import enum
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.service import get_or_create_default_agent, record_action, request_access
from app.channels.schema import NormalizedEvent
from app.db.models import ActionStatus, Channel, Direction
from app.graph import run_turn
from app.security.auth import authorize
from app.security.hashing import channel_identifier_key

logger = logging.getLogger("channelagent")

DENIED_MESSAGE = (
    "You're not authorized to use this bot yet. An admin has been notified of your request."
)

# Channels where an unauthorized sender gets an AccessRequest but no
# reply. An email's From address can be forged, so answering it would
# send mail to a third party, and the mailbox is shared with ordinary
# customer mail.
SILENT_DENIAL_CHANNELS = frozenset({Channel.EMAIL})


class DispatchOutcome(enum.StrEnum):
    OK = "ok"  # answered and delivered
    DENIED = "denied"  # not authorized, nothing to retry
    FAILED = "failed"  # the turn or the delivery failed (#51)


APOLOGY_MESSAGE = "Sorry, I cannot answer right now. Please try again in a few minutes."
NO_REPLY_NOTE = "(the turn failed, no reply was sent)"
AGENT_DISABLED_MESSAGE = "This agent is currently disabled. Please contact an administrator."


async def dispatch_event(
    session: AsyncSession,
    event: NormalizedEvent,
    *,
    apologize: bool = True,
    retry: bool = False,
) -> DispatchOutcome:
    """Authorize, run the graph, deliver the reply, and record every step.

    Failures never escape (#51): the inbound message is committed to the
    audit trail *before* the LLM is called, so a failed turn cannot lose
    it; a failed turn is recorded with status "failed" and, when
    `apologize` is set, answered with a fixed apology (never an error
    text). The caller learns the outcome and decides about retrying.

    `retry` is for a message that is being processed again: the inbound
    entry already exists and is not written twice. `apologize=False` is
    for channels that retry silently (email).
    """
    decision = await authorize(session, event.channel, event.user_id)

    if not decision.allowed:
        logger.info("Denied %s/%s: not authorized", event.channel.value, event.user_id)
        key = channel_identifier_key(event.channel, event.user_id)
        await request_access(session, event.channel, key, event.text)
        if decision.user is not None:
            agent = await get_or_create_default_agent(session, decision.user.id)
            await record_action(
                session, user_id=decision.user.id, agent_id=agent.id, channel=event.channel,
                direction=Direction.INBOUND, text=event.text, status=ActionStatus.DENIED,
            )
        await session.commit()
        if event.channel not in SILENT_DENIAL_CHANNELS:
            await event.reply(DENIED_MESSAGE)
        return DispatchOutcome.DENIED

    agent = await get_or_create_default_agent(session, decision.user.id)
    user_id, agent_id = decision.user.id, agent.id
    if not agent.is_active:
        # Deactivating an agent has to stop it answering (#37): no LLM call.
        logger.info(
            "Agent %s of %s/%s is deactivated", agent_id, event.channel.value, event.user_id
        )
        await record_action(
            session, user_id=user_id, agent_id=agent_id, channel=event.channel,
            direction=Direction.INBOUND, text=event.text, status=ActionStatus.DENIED,
        )
        await session.commit()
        try:
            await event.reply(AGENT_DISABLED_MESSAGE)
        except Exception:
            logger.exception("Sending the disabled-agent notice to %s failed", event.user_id)
        return DispatchOutcome.DENIED
    if not retry:
        await record_action(
            session, user_id=user_id, agent_id=agent_id, channel=event.channel,
            direction=Direction.INBOUND, text=event.text,
        )
    await session.commit()

    try:
        reply_text = await run_turn(event.channel, event.user_id, agent_id, event.text)
    except Exception:
        logger.exception("Turn failed for %s/%s", event.channel.value, event.user_id)
        sent = False
        if apologize:
            try:
                await event.reply(APOLOGY_MESSAGE)
                sent = True
            except Exception:
                logger.exception(
                    "Sending the apology to %s/%s failed", event.channel.value, event.user_id
                )
        await record_action(
            session, user_id=user_id, agent_id=agent_id, channel=event.channel,
            direction=Direction.OUTBOUND, text=APOLOGY_MESSAGE if sent else NO_REPLY_NOTE,
            status=ActionStatus.FAILED,
        )
        await session.commit()
        return DispatchOutcome.FAILED

    outbound = await record_action(
        session, user_id=user_id, agent_id=agent_id, channel=event.channel,
        direction=Direction.OUTBOUND, text=reply_text,
    )
    await session.commit()
    try:
        await event.reply(reply_text)
    except Exception:
        logger.exception("Delivering the reply to %s/%s failed", event.channel.value, event.user_id)
        outbound.status = ActionStatus.FAILED
        await session.commit()
        return DispatchOutcome.FAILED
    return DispatchOutcome.OK
