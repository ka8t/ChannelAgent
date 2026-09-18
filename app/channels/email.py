"""Email (IMAP/SMTP) channel adapter (#28): polls IMAP for new
messages, normalizes them, and routes them through the shared dispatch
pipeline (app/channels/dispatch.py) — same shape as the Telegram
adapter (app/channels/telegram.py), IMAP/SMTP instead of the Bot API.

IMAP/SMTP calls are synchronous (stdlib imaplib/smtplib) — wrapped in
asyncio.to_thread so a slow mail server doesn't block the event loop
the Telegram adapter and Admin API also run in.
"""

import asyncio
import email
import email.utils
import imaplib
import logging
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText

from app.channels.dispatch import dispatch_event
from app.channels.schema import NormalizedEvent
from app.config import get_settings
from app.db.models import Channel
from app.db.session import session_scope

logger = logging.getLogger("channelagent")

POLL_INTERVAL_SECONDS = 15


def _decode(value: str) -> str:
    parts = decode_header(value)
    return "".join(
        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else str(part)
        for part, enc in parts
    )


def _extract_body(msg: "email.message.Message") -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                return payload.decode(charset, errors="replace") if payload else ""
        return ""
    charset = msg.get_content_charset() or "utf-8"
    payload = msg.get_payload(decode=True)
    return payload.decode(charset, errors="replace") if payload else ""


def _fetch_unseen() -> list[tuple[str, str, str]]:
    """Sync IMAP work: connect, fetch UNSEEN messages, mark them Seen,
    disconnect. Returns (from_address, subject, body) tuples.
    """
    settings = get_settings()
    imap = imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port, timeout=10)
    results: list[tuple[str, str, str]] = []
    try:
        imap.login(settings.email_username, settings.email_password)
        imap.select("INBOX")
        typ, data = imap.search(None, "UNSEEN")
        if typ == "OK":
            for num in data[0].split():
                typ, msg_data = imap.fetch(num, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                from_addr = email.utils.parseaddr(msg.get("From", ""))[1]
                subject = _decode(msg.get("Subject", ""))
                body = _extract_body(msg).strip()
                if from_addr and body:
                    results.append((from_addr, subject, body))
                imap.store(num, "+FLAGS", "\\Seen")
    finally:
        try:
            imap.logout()
        except Exception:
            logger.debug("IMAP logout raised, ignoring", exc_info=True)
    return results


def _send_reply_sync(to_address: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.email_username
    msg["To"] = to_address
    with smtplib.SMTP_SSL(settings.email_smtp_host, settings.email_smtp_port, timeout=10) as smtp:
        smtp.login(settings.email_username, settings.email_password)
        smtp.send_message(msg)


async def _poll_once() -> None:
    messages = await asyncio.to_thread(_fetch_unseen)
    for from_addr, subject, body in messages:
        logger.info("Email received from %s: %s", from_addr, subject)

        async def reply(text: str, _to: str = from_addr, _subj: str = subject) -> None:
            await asyncio.to_thread(_send_reply_sync, _to, f"Re: {_subj}", text)

        event = NormalizedEvent(user_id=from_addr, channel=Channel.EMAIL, text=body, reply=reply)
        async with session_scope() as session:
            await dispatch_event(session, event)


async def run_email_adapter() -> None:
    """Runs until cancelled — polls IMAP every POLL_INTERVAL_SECONDS."""
    logger.info("Email adapter started (polling every %ss).", POLL_INTERVAL_SECONDS)
    while True:
        try:
            await _poll_once()
        except Exception:
            logger.exception("Email poll failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
