"""Normalized event schema every channel adapter must produce (#26).

The Auth Node and app/graph.py only ever see this shape — neither
imports anything Telegram/Email/Matrix-specific, per
docs/ARCHITECTURE.md.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.db.models import Channel


@dataclass
class NormalizedEvent:
    user_id: str
    channel: Channel
    text: str
    # How to deliver the agent's reply back through the channel this
    # event arrived on (#17) — e.g. a Telegram adapter's closure over
    # bot.send_message(chat_id, ...). Only app.channels.dispatch calls
    # this; app/graph.py and the Auth Node never see it.
    reply: Callable[[str], Awaitable[None]]
