"""Tests for #28: email parsing helpers (offline, real email.message
objects, no network) and dispatch wiring via Channel.EMAIL (mock LLM,
reusing the pattern already proven for Telegram).
"""

import email
import json
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.channels import email as email_adapter
from app.channels.email import _decode, _extract_body, _fetch_tagged_unseen


def test_decode_plain_ascii_subject():
    assert _decode("Hello world") == "Hello world"


def test_decode_rfc2047_encoded_subject():
    # A real MIME-encoded header, as a non-ASCII subject actually arrives.
    encoded = "=?utf-8?b?QsOgIGVzc2Fp?="  # "Bà essai"
    assert _decode(encoded) == "Bà essai"


def test_extract_body_plain_text_message():
    msg = MIMEText("hello from a plain message", "plain", "utf-8")
    parsed = email.message_from_bytes(msg.as_bytes())
    assert _extract_body(parsed).strip() == "hello from a plain message"


def test_extract_body_multipart_prefers_plain_text_part():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("plain version", "plain", "utf-8"))
    msg.attach(MIMEText("<p>html version</p>", "html", "utf-8"))
    parsed = email.message_from_bytes(msg.as_bytes())
    assert _extract_body(parsed).strip() == "plain version"


class _MockLlama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)
        resp = {"choices": [{"message": {"role": "assistant", "content": "email reply"}}]}
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.mark.asyncio
async def test_dispatch_event_over_email_channel(fresh_db, monkeypatch):
    server = HTTPServer(("127.0.0.1", 8095), _MockLlama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://127.0.0.1:8095")
    from app import config

    config.get_settings.cache_clear()

    from app.channels.dispatch import dispatch_event
    from app.channels.schema import NormalizedEvent
    from app.db.models import Channel, ChannelIdentity, PermissionKind, User
    from app.db.session import init_db, session_scope
    from app.security.auth import grant_permission
    from app.security.hashing import hash_email

    await init_db()
    async with session_scope() as session:
        user = User(display_name="Email test")
        session.add(user)
        await session.flush()
        identity = ChannelIdentity(
            user_id=user.id,
            channel=Channel.EMAIL,
            external_id=hash_email("sender@example.com"),
            raw_address="sender@example.com",
        )
        session.add(identity)
        await session.flush()
        await grant_permission(session, identity, PermissionKind.CHAT)
        await session.commit()

    sent = []

    async def reply(text: str) -> None:
        sent.append(text)

    async with session_scope() as session:
        event = NormalizedEvent(
            user_id="sender@example.com", channel=Channel.EMAIL, text="hi", reply=reply
        )
        await dispatch_event(session, event)

    assert sent == ["email reply"]
    server.shutdown()
    config.get_settings.cache_clear()


# --- Shared mailbox: only messages carrying the trigger tag are touched ---


def _raw(sender: str, subject: str, body: str) -> bytes:
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = sender
    msg["Subject"] = subject
    return msg.as_bytes()


class _FakeIMAP:
    """Records every command so a test can count what was fetched,
    flagged, created and moved. Messages are addressed by UID, like the
    adapter does.

    search_ignores_subject simulates a server that does not honour
    SEARCH SUBJECT, so the client-side check is what protects.
    capabilities controls whether MOVE / UIDPLUS are advertised.
    """

    def __init__(
        self,
        messages: dict[bytes, bytes],
        search_ignores_subject: bool = False,
        capabilities: tuple[str, ...] = ("IMAP4REV1", "MOVE", "UIDPLUS"),
        folders: set[str] | None = None,
        create_fails: bool = False,
    ):
        self.messages = dict(messages)
        self.search_ignores_subject = search_ignores_subject
        self.capabilities = capabilities
        self.folders = set(folders or {"INBOX"})
        self.create_fails = create_fails
        self.fetches: list[tuple[bytes, str]] = []
        self.stores: list[tuple[bytes, str, str]] = []
        self.moves: list[tuple[bytes, str]] = []
        self.copies: list[tuple[bytes, str]] = []
        self.uid_expunges: list[bytes] = []
        self.plain_expunges = 0
        self.creates: list[str] = []
        self.subscribes: list[str] = []
        self.lists = 0
        self.filed: dict[str, list[bytes]] = {}

    def login(self, *a):
        return "OK", []

    def select(self, *a):
        return "OK", [b"1"]

    def list(self, directory='""', pattern="*"):
        self.lists += 1
        name = pattern.strip('"')
        if name in self.folders:
            return "OK", [f'(\\HasNoChildren) "." "{name}"'.encode()]
        return "OK", [None]

    def create(self, folder):
        self.creates.append(folder)
        if self.create_fails:
            return "NO", [b"permission denied"]
        self.folders.add(folder)
        return "OK", [b"created"]

    def subscribe(self, folder):
        self.subscribes.append(folder)
        return "OK", []

    def expunge(self):
        self.plain_expunges += 1
        return "OK", []

    def uid(self, command, *args):
        command = command.upper()
        if command == "SEARCH":
            uids = list(self.messages)
            if "SUBJECT" in args and not self.search_ignores_subject:
                wanted = args[args.index("SUBJECT") + 1].strip('"').lower()
                uids = [
                    u for u in uids
                    if wanted in email.message_from_bytes(self.messages[u])["Subject"].lower()
                ]
            return "OK", [b" ".join(uids)]
        if command == "FETCH":
            uid, spec = args
            self.fetches.append((uid, spec))
            return "OK", [(b"1 (UID 1 BODY[] {0}", self.messages[uid]), b")"]
        if command == "STORE":
            uid, cmd, flags = args
            self.stores.append((uid, cmd, flags))
            return "OK", []
        if command == "MOVE":
            uid, folder = args
            self.moves.append((uid, folder))
            self.messages.pop(uid, None)
            self.filed.setdefault(folder, []).append(uid)
            return "OK", []
        if command == "COPY":
            uid, folder = args
            self.copies.append((uid, folder))
            self.filed.setdefault(folder, []).append(uid)
            return "OK", []
        if command == "EXPUNGE":
            (uid,) = args
            self.uid_expunges.append(uid)
            self.messages.pop(uid, None)
            return "OK", []
        raise AssertionError(f"unexpected UID command {command}")

    def logout(self):
        return "BYE", []


@pytest.fixture
def fake_imap(monkeypatch):
    holder = {"connections": 0}

    def install(messages, **kwargs):
        fake = _FakeIMAP(messages, **kwargs)

        def factory(*a, **k):
            holder["connections"] += 1
            return fake

        monkeypatch.setattr(email_adapter.imaplib, "IMAP4_SSL", factory)
        monkeypatch.setattr(
            email_adapter,
            "get_settings",
            lambda: type("S", (), {
                "email_imap_host": "h", "email_imap_port": 993,
                "email_username": "u", "email_password": "p",
            })(),
        )
        return fake

    install.holder = holder
    return install


CUSTOMER = ("customer@example.com", "Question about your offer", "not for the bot")
TAGGED = ("sender@example.com", "Re: [Agent] hello", "for the bot")


def test_untagged_messages_are_never_fetched_flagged_or_moved(fake_imap):
    fake = fake_imap({
        b"11": _raw(*CUSTOMER),
        b"12": _raw("other@example.com", "Contact form", "hi"),
    })
    assert _fetch_tagged_unseen("[agent]", "INBOX.Agent") == []
    assert fake.fetches == [] and fake.stores == []
    assert fake.moves == [] and fake.creates == [] and fake.lists == 0


def test_tagged_message_is_read_with_peek_flagged_seen_and_filed(fake_imap):
    fake = fake_imap({b"11": _raw(*CUSTOMER), b"12": _raw(*TAGGED)})
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert result == [("sender@example.com", "Re: [Agent] hello", "for the bot")]
    assert [u for u, _ in fake.fetches] == [b"12"]
    assert all("PEEK" in spec for _, spec in fake.fetches)
    assert fake.stores == [(b"12", "+FLAGS", "\\Seen")]
    assert fake.moves == [(b"12", "INBOX.Agent")]
    assert fake.creates == ["INBOX.Agent"] and fake.subscribes == ["INBOX.Agent"]
    assert list(fake.messages) == [b"11"], "the customer mail must still be in the INBOX"
    assert fake.plain_expunges == 0


def test_client_side_check_protects_when_server_ignores_subject_search(fake_imap):
    fake = fake_imap(
        {b"11": _raw(*CUSTOMER), b"12": _raw("s@example.com", "[agent] hello", "for the bot")},
        search_ignores_subject=True,
    )
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert [r[0] for r in result] == ["s@example.com"]
    assert all("PEEK" in spec for _, spec in fake.fetches)
    assert fake.stores == [(b"12", "+FLAGS", "\\Seen")]
    assert fake.moves == [(b"12", "INBOX.Agent")]
    assert b"11" in fake.messages


def test_two_tagged_messages_are_both_handled_and_folder_is_created_once(fake_imap):
    fake = fake_imap({
        b"21": _raw("a@example.com", "[agent] first", "one"),
        b"22": _raw("b@example.com", "[agent] second", "two"),
    })
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert [r[0] for r in result] == ["a@example.com", "b@example.com"]
    assert fake.moves == [(b"21", "INBOX.Agent"), (b"22", "INBOX.Agent")]
    assert fake.creates == ["INBOX.Agent"]


def test_existing_folder_is_not_recreated(fake_imap):
    fake = fake_imap({b"12": _raw(*TAGGED)}, folders={"INBOX", "INBOX.Agent"})
    _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert fake.creates == []
    assert fake.moves == [(b"12", "INBOX.Agent")]


def test_without_move_falls_back_to_copy_flag_and_uid_expunge_of_that_uid_only(fake_imap):
    fake = fake_imap(
        {b"11": _raw(*CUSTOMER), b"12": _raw(*TAGGED)},
        capabilities=("IMAP4REV1", "UIDPLUS"),
    )
    _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert fake.moves == []
    assert fake.copies == [(b"12", "INBOX.Agent")]
    assert (b"12", "+FLAGS", "\\Deleted") in fake.stores
    assert fake.uid_expunges == [b"12"]
    assert fake.plain_expunges == 0
    assert b"11" in fake.messages


def test_without_move_or_uidplus_nothing_is_moved_or_expunged(fake_imap):
    fake = fake_imap({b"12": _raw(*TAGGED)}, capabilities=("IMAP4REV1",))
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert len(result) == 1, "the message must still be handled"
    assert fake.stores == [(b"12", "+FLAGS", "\\Seen")]
    assert fake.moves == [] and fake.copies == []
    assert fake.uid_expunges == [] and fake.plain_expunges == 0


def test_folder_creation_failure_still_handles_the_message(fake_imap):
    fake = fake_imap({b"12": _raw(*TAGGED)}, create_fails=True)
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert len(result) == 1
    assert fake.moves == [] and fake.copies == []
    assert b"12" in fake.messages, "it stays in the INBOX when it cannot be filed"


@pytest.mark.parametrize("folder", ["", "   "])
def test_empty_folder_setting_leaves_messages_in_the_inbox(fake_imap, folder):
    fake = fake_imap({b"12": _raw(*TAGGED)})
    result = _fetch_tagged_unseen("[agent]", folder)
    assert len(result) == 1
    assert fake.stores == [(b"12", "+FLAGS", "\\Seen")]
    assert fake.lists == 0 and fake.creates == [] and fake.moves == []


@pytest.mark.parametrize("folder", ['a"b', "a\\b", "In*box", "Bo%x", "dossié"])
def test_unusable_folder_name_moves_nothing_but_still_handles_the_message(fake_imap, folder):
    fake = fake_imap({b"12": _raw(*TAGGED)})
    result = _fetch_tagged_unseen("[agent]", folder)
    assert len(result) == 1
    assert fake.lists == 0 and fake.creates == [] and fake.moves == [] and fake.copies == []


@pytest.mark.parametrize("tag", ["", "   ", 'a"b', "a\\b", "é-tag"])
def test_unusable_tag_processes_nothing_and_never_connects(fake_imap, tag):
    fake = fake_imap({b"12": _raw("sender@example.com", "anything", "body")})
    assert _fetch_tagged_unseen(tag, "INBOX.Agent") == []
    assert fake_imap.holder["connections"] == 0
    assert fake.fetches == [] and fake.stores == [] and fake.moves == []


def test_default_trigger_tag_and_folder(monkeypatch):
    monkeypatch.delenv("EMAIL_TRIGGER_TAG", raising=False)
    monkeypatch.delenv("EMAIL_AGENT_FOLDER", raising=False)
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.email_trigger_tag == "[agent]"
    assert settings.email_agent_folder == "INBOX.Agent"


@pytest.mark.asyncio
async def test_unknown_email_sender_gets_a_request_but_no_reply(fresh_db):
    from sqlalchemy import func, select

    from app.channels.dispatch import dispatch_event
    from app.channels.schema import NormalizedEvent
    from app.db.models import AccessRequest, Channel
    from app.db.session import init_db, session_scope

    await init_db()
    sent: list[str] = []

    async def reply(text: str) -> None:
        sent.append(text)

    async with session_scope() as session:
        await dispatch_event(
            session, NormalizedEvent("stranger@example.com", Channel.EMAIL, "let me in", reply)
        )
    async with session_scope() as session:
        n = (await session.execute(select(func.count()).select_from(AccessRequest))).scalar_one()
    assert sent == []
    assert n == 1


@pytest.mark.asyncio
async def test_unknown_telegram_sender_still_gets_the_denial_reply(fresh_db):
    from app.channels.dispatch import DENIED_MESSAGE, dispatch_event
    from app.channels.schema import NormalizedEvent
    from app.db.models import Channel
    from app.db.session import init_db, session_scope

    await init_db()
    sent: list[str] = []

    async def reply(text: str) -> None:
        sent.append(text)

    async with session_scope() as session:
        await dispatch_event(session, NormalizedEvent("424242", Channel.TELEGRAM, "hi", reply))
    assert sent == [DENIED_MESSAGE]


def test_imap_error_while_moving_does_not_lose_the_message(fake_imap):
    fake = fake_imap({b"12": _raw(*TAGGED)})
    original = fake.uid

    def uid(command, *args):
        if command.upper() == "MOVE":
            raise email_adapter.imaplib.IMAP4.error("boom")
        return original(command, *args)

    fake.uid = uid
    result = _fetch_tagged_unseen("[agent]", "INBOX.Agent")
    assert len(result) == 1
    assert fake.stores == [(b"12", "+FLAGS", "\\Seen")]
    assert b"12" in fake.messages
