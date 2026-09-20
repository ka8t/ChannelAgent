"""Tests for #27: the Telegram adapter's own behavior, without the network:
what it ignores, how it normalizes, how it replies, how it polls.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.channels import telegram
from app.db.models import Channel


def _update(text="hello", user_id=55, chat_id=999, message=True, user=True):
    return SimpleNamespace(
        message=SimpleNamespace(text=text) if message else None,
        effective_user=SimpleNamespace(id=user_id) if user else None,
        effective_chat=SimpleNamespace(id=chat_id),
    )


class _Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))


@pytest.fixture
def spy(monkeypatch):
    events = []

    async def fake_dispatch(session, event, **kwargs):
        events.append(event)

    monkeypatch.setattr(telegram, "dispatch_event", fake_dispatch)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_scope():
        yield object()

    monkeypatch.setattr(telegram, "session_scope", fake_scope)
    return events


@pytest.mark.parametrize(
    "update",
    [
        _update(message=False),
        _update(text=None),
        _update(user=False),
    ],
    ids=["no message", "no text (photo, sticker...)", "no user"],
)
async def test_updates_without_text_or_user_are_ignored(spy, update):
    await telegram._on_message(update, SimpleNamespace(bot=_Bot()))
    assert spy == []


async def test_a_text_message_becomes_a_normalized_event(spy):
    await telegram._on_message(_update("hi there", user_id=55), SimpleNamespace(bot=_Bot()))
    assert len(spy) == 1
    event = spy[0]
    assert (event.user_id, event.channel, event.text) == ("55", Channel.TELEGRAM, "hi there")


async def test_the_user_id_is_a_string_so_it_matches_the_stored_identity(spy):
    await telegram._on_message(_update(user_id=7231548225), SimpleNamespace(bot=_Bot()))
    assert spy[0].user_id == "7231548225" and isinstance(spy[0].user_id, str)


async def test_the_reply_callback_sends_to_the_chat_the_message_came_from(spy):
    bot = _Bot()
    await telegram._on_message(_update(chat_id=4242), SimpleNamespace(bot=bot))
    await spy[0].reply("the answer")
    assert bot.sent == [(4242, "the answer")]


def test_building_the_application_requires_a_token(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        telegram.build_application()


class _StubBot:
    """CommandHandler reads the bot's username to recognize /command@bot."""

    username = "testbot"


def _real_update(text: str, entities=None):
    from telegram import Update

    return Update.de_json(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1_700_000_000,
                "chat": {"id": 1, "type": "private"},
                "from": {"id": 55, "is_bot": False, "first_name": "A"},
                "text": text,
                **({"entities": entities} if entities else {}),
            },
        },
        _StubBot(),
    )


def test_the_handlers_take_plain_text_and_the_agent_command_only(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF-test-token")
    get_settings.cache_clear()
    application = telegram.build_application()
    handlers = [h for group in application.handlers.values() for h in group]
    assert len(handlers) == 2
    by_callback = {h.callback: h for h in handlers}
    text_handler, agent_handler = by_callback[telegram._on_message], by_callback[telegram._on_agent]

    def command(name, arg=""):
        text = f"/{name} {arg}".strip()
        return _real_update(text, [{"type": "bot_command", "offset": 0, "length": len(name) + 1}])

    assert text_handler.check_update(_real_update("hello")) is not None
    assert not text_handler.check_update(command("agent", "work")), "commands are not plain text"
    assert agent_handler.check_update(command("agent", "work")) is not None
    assert agent_handler.check_update(command("agent")) is not None
    assert not agent_handler.check_update(_real_update("hello"))
    assert not agent_handler.check_update(command("start")), "other commands stay ignored"
    assert not text_handler.check_update(command("start"))


class _FakeApplication:
    def __init__(self):
        self.calls = []
        self.updater = SimpleNamespace(start_polling=self._start_polling, stop=self._updater_stop)

    async def __aenter__(self):
        self.calls.append("enter")
        return self

    async def __aexit__(self, *exc):
        self.calls.append("exit")

    async def start(self):
        self.calls.append("start")

    async def stop(self):
        self.calls.append("stop")

    async def _start_polling(self, **kwargs):
        self.calls.append(("start_polling", kwargs))

    async def _updater_stop(self):
        self.calls.append("updater_stop")


async def test_the_adapter_polls_dropping_pending_updates_and_stops_cleanly(monkeypatch):
    fake = _FakeApplication()
    monkeypatch.setattr(telegram, "build_application", lambda: fake)
    task = asyncio.create_task(telegram.run_telegram_adapter())
    for _ in range(50):
        await asyncio.sleep(0.01)
        if ("start_polling", {"drop_pending_updates": True}) in fake.calls:
            break
    assert ("start_polling", {"drop_pending_updates": True}) in fake.calls
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake.calls[-3:] == ["updater_stop", "stop", "exit"], "shut down in order on cancel"
