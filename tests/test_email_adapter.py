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

from app.channels.email import _decode, _extract_body


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
