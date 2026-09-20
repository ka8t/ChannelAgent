"""Tests for #51: a failed turn must be visible to the user, recorded in
the audit trail, and must never raise out of dispatch_event.
"""

import sqlite3

import pytest

from app.channels.dispatch import (
    APOLOGY_MESSAGE,
    DENIED_MESSAGE,
    NO_REPLY_NOTE,
    DispatchOutcome,
    dispatch_event,
)
from app.channels.schema import NormalizedEvent
from app.db.models import Channel


def _rows():
    from app.config import get_settings

    db = get_settings().database_url.split("///", 1)[1]
    con = sqlite3.connect(db)
    try:
        return con.execute(
            "select direction, status from action_logs order by id"
        ).fetchall()
    finally:
        con.close()


@pytest.fixture
async def authorized(fresh_db):
    from app.db.models import ChannelIdentity, PermissionKind, User
    from app.db.session import init_db, session_scope
    from app.security.auth import grant_permission

    await init_db()
    async with session_scope() as s:
        u = User(display_name="Alice")
        s.add(u)
        await s.flush()
        ident = ChannelIdentity(user_id=u.id, channel=Channel.TELEGRAM, external_id="55")
        s.add(ident)
        await s.flush()
        await grant_permission(s, ident, PermissionKind.CHAT)
        await s.commit()


class _Sink:
    def __init__(self, fail=False):
        self.sent: list[str] = []
        self.fail = fail

    async def reply(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("channel down")
        self.sent.append(text)


async def _dispatch(user="55", channel=Channel.TELEGRAM, sink=None, **kwargs):
    from app.db.session import session_scope

    sink = sink or _Sink()
    event = NormalizedEvent(user, channel, "hello", sink.reply)
    async with session_scope() as session:
        outcome = await dispatch_event(session, event, **kwargs)
    return outcome, sink


@pytest.fixture
def llm_down(monkeypatch):
    """A real connection error: nothing listens on port 1."""
    from app.config import get_settings

    monkeypatch.setenv("LLAMA_SERVER_URL", "http://127.0.0.1:1")
    get_settings.cache_clear()


@pytest.fixture
def llm_up(monkeypatch):
    async def fake(channel, user_id, agent_id, text):
        return "the answer"

    monkeypatch.setattr("app.channels.dispatch.run_turn", fake)


async def test_llm_unreachable_apologizes_and_keeps_the_inbound_message(authorized, llm_down):
    outcome, sink = await _dispatch()
    assert outcome is DispatchOutcome.FAILED
    assert sink.sent == [APOLOGY_MESSAGE], "exactly one apology, no error detail"
    assert _rows() == [("inbound", "ok"), ("outbound", "failed")]


async def test_the_apology_never_contains_error_details(authorized, llm_down):
    _, sink = await _dispatch()
    assert "127.0.0.1" not in sink.sent[0] and "Connect" not in sink.sent[0]


async def test_apologize_false_sends_nothing_but_still_records_the_failure(authorized, llm_down):
    from app.admin import service
    from app.db.session import session_scope

    outcome, sink = await _dispatch(apologize=False)
    assert outcome is DispatchOutcome.FAILED
    assert sink.sent == []
    assert _rows() == [("inbound", "ok"), ("outbound", "failed")]
    async with session_scope() as s:
        texts = [e.text for e in await service.search_action_logs(s)]
    assert NO_REPLY_NOTE in texts


async def test_a_retry_does_not_write_the_inbound_message_twice(authorized, llm_down):
    await _dispatch(apologize=False)
    await _dispatch(apologize=False, retry=True)
    await _dispatch(apologize=False, retry=True)
    assert _rows() == [
        ("inbound", "ok"), ("outbound", "failed"), ("outbound", "failed"), ("outbound", "failed"),
    ]


async def test_failing_apology_delivery_does_not_raise(authorized, llm_down):
    outcome, _ = await _dispatch(sink=_Sink(fail=True))
    assert outcome is DispatchOutcome.FAILED
    assert _rows() == [("inbound", "ok"), ("outbound", "failed")]


async def test_a_successful_turn_is_ok_ok(authorized, llm_up):
    outcome, sink = await _dispatch()
    assert outcome is DispatchOutcome.OK
    assert sink.sent == ["the answer"]
    assert _rows() == [("inbound", "ok"), ("outbound", "ok")]


async def test_delivery_failure_is_failed_and_keeps_the_generated_answer(authorized, llm_up):
    from app.admin import service
    from app.db.models import ActionStatus
    from app.db.session import session_scope

    outcome, _ = await _dispatch(sink=_Sink(fail=True))
    assert outcome is DispatchOutcome.FAILED
    assert _rows() == [("inbound", "ok"), ("outbound", "failed")]
    async with session_scope() as s:
        failed = await service.search_action_logs(s, status=ActionStatus.FAILED)
    assert [e.text for e in failed] == ["the answer"], "the undelivered answer is not lost"


async def test_denied_known_identity_is_recorded_as_denied(fresh_db):
    from app.db.models import ChannelIdentity, User
    from app.db.session import init_db, session_scope

    await init_db()
    async with session_scope() as s:
        u = User(display_name="No permission")
        s.add(u)
        await s.flush()
        s.add(ChannelIdentity(user_id=u.id, channel=Channel.TELEGRAM, external_id="66"))
        await s.commit()
    outcome, sink = await _dispatch(user="66")
    assert outcome is DispatchOutcome.DENIED
    assert sink.sent == [DENIED_MESSAGE]
    assert _rows() == [("inbound", "denied")]


async def test_unknown_identity_is_denied_without_a_log_row(fresh_db):
    from app.db.session import init_db

    await init_db()
    outcome, sink = await _dispatch(user="777")
    assert outcome is DispatchOutcome.DENIED
    assert sink.sent == [DENIED_MESSAGE]
    assert _rows() == []


async def test_unknown_email_sender_gets_no_reply(fresh_db):
    from app.db.session import init_db

    await init_db()
    outcome, sink = await _dispatch(user="stranger@example.com", channel=Channel.EMAIL)
    assert outcome is DispatchOutcome.DENIED
    assert sink.sent == []


async def test_telegram_adapter_path_survives_a_failed_turn(authorized, llm_down):
    """The Telegram handler calls dispatch_event with defaults: the user
    gets the apology and nothing is raised into python-telegram-bot.
    """
    from types import SimpleNamespace

    from app.channels import telegram

    sent = []

    class Bot:
        async def send_message(self, chat_id, text):
            sent.append((chat_id, text))

    update = SimpleNamespace(
        message=SimpleNamespace(text="hello"),
        effective_user=SimpleNamespace(id=55),
        effective_chat=SimpleNamespace(id=999),
    )
    await telegram._on_message(update, SimpleNamespace(bot=Bot()))
    assert sent == [(999, APOLOGY_MESSAGE)]
    assert _rows() == [("inbound", "ok"), ("outbound", "failed")]
