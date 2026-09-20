"""Email (IMAP/SMTP) channel adapter (#28): polls IMAP for new
messages, normalizes them, and routes them through the shared dispatch
pipeline (app/channels/dispatch.py) — same shape as the Telegram
adapter (app/channels/telegram.py), IMAP/SMTP instead of the Bot API.

The mailbox is shared with ordinary mail (website contact form,
customer questions), so the adapter only touches messages whose subject
contains EMAIL_TRIGGER_TAG. Every other message is never fetched,
flagged or answered: it stays unread for a human. Messages are read with
BODY.PEEK, which sets no flag, and only tagged ones are then marked Seen
and filed into EMAIL_AGENT_FOLDER, so they leave the INBOX humans read.
Nothing is ever deleted or purged automatically.

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


def _tag_is_usable(tag: str) -> bool:
    """The tag goes into an IMAP SEARCH string, so it must be plain
    ASCII with nothing that needs escaping. An empty tag is unusable on
    purpose: it would match every message in the shared mailbox.
    """
    return bool(tag.strip()) and tag.isascii() and '"' not in tag and "\\" not in tag


def _subject_has_tag(subject: str, tag: str) -> bool:
    return _tag_is_usable(tag) and tag.lower() in subject.lower()


def _folder_is_usable(folder: str) -> bool:
    """The folder name goes into IMAP commands unescaped, so it must be
    plain ASCII without quotes, backslashes or wildcards. Empty is valid
    and means "do not move handled messages".
    """
    return not folder.strip() or (
        folder.isascii() and not any(c in folder for c in '"\\*%')
    )


def _ensure_folder(imap: imaplib.IMAP4, folder: str) -> bool:
    """Create the agent folder if it does not exist yet, and subscribe to
    it so webmail clients list it. Returns whether it exists afterwards.
    """
    typ, data = imap.list(pattern=f'"{folder}"')
    exists = typ == "OK" and any(item for item in data)
    if not exists:
        typ, _ = imap.create(folder)
        if typ != "OK":
            return False
    imap.subscribe(folder)
    return True


def _move_message(imap: imaplib.IMAP4, uid: bytes, folder: str) -> bool:
    """File one message, addressed by UID, into `folder`.

    Prefers MOVE. Without it, COPY then flag Deleted then UID EXPUNGE,
    which only removes this UID. A plain EXPUNGE is never used: it would
    also remove any message a human client flagged Deleted but has not
    expunged yet. Without UIDPLUS (needed for UID EXPUNGE) nothing is
    moved at all.
    """
    caps = getattr(imap, "capabilities", ())
    if "MOVE" in caps and "MOVE" in imaplib.Commands:
        typ, _ = imap.uid("MOVE", uid, folder)
        return typ == "OK"
    if "UIDPLUS" in caps:
        typ, _ = imap.uid("COPY", uid, folder)
        if typ != "OK":
            return False
        imap.uid("STORE", uid, "+FLAGS", "\\Deleted")
        imap.uid("EXPUNGE", uid)
        return True
    return False


def _fetch_tagged_unseen(tag: str, folder: str = "") -> list[tuple[str, str, str]]:
    """Sync IMAP work: connect, find UNSEEN messages whose subject
    carries the trigger tag, fetch only those (BODY.PEEK, so the fetch
    itself sets no flag), mark only those Seen, move only those into
    `folder` (when set), disconnect. Returns (from_address, subject,
    body) tuples.

    Everything is addressed by UID, not by message number: a move
    renumbers the messages that follow it in the same session.

    The server-side SEARCH narrows the set, and the subject is checked
    again here because servers differ in how they match SUBJECT. A
    message that fails that check is never marked Seen or moved. A
    failed move is logged and never blocks the message from being handled:
    it has already been read and marked Seen at that point.
    """
    if not _tag_is_usable(tag):
        return []
    if not _folder_is_usable(folder):
        logger.error("EMAIL_AGENT_FOLDER %r is not usable, handled mail stays in INBOX", folder)
        folder = ""
    folder = folder.strip()
    settings = get_settings()
    imap = imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port, timeout=10)
    results: list[tuple[str, str, str]] = []
    folder_ready: bool | None = None
    try:
        imap.login(settings.email_username, settings.email_password)
        imap.select("INBOX")
        typ, data = imap.uid("SEARCH", "UNSEEN", "SUBJECT", f'"{tag}"')
        if typ == "OK":
            for uid in data[0].split():
                typ, msg_data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode(msg.get("Subject", ""))
                if not _subject_has_tag(subject, tag):
                    continue
                from_addr = email.utils.parseaddr(msg.get("From", ""))[1]
                body = _extract_body(msg).strip()
                if from_addr and body:
                    results.append((from_addr, subject, body))
                imap.uid("STORE", uid, "+FLAGS", "\\Seen")
                if folder:
                    try:
                        if folder_ready is None:
                            folder_ready = _ensure_folder(imap, folder)
                        if not folder_ready or not _move_message(imap, uid, folder):
                            logger.warning(
                                "Could not move message %s to %r, it stays in INBOX",
                                uid.decode(), folder,
                            )
                    except imaplib.IMAP4.error:
                        logger.warning(
                            "IMAP error moving message %s to %r, it stays in INBOX",
                            uid.decode(), folder, exc_info=True,
                        )
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
    settings = get_settings()
    messages = await asyncio.to_thread(
        _fetch_tagged_unseen, settings.email_trigger_tag, settings.email_agent_folder
    )
    for from_addr, subject, body in messages:
        logger.info("Email received from %s: %s", from_addr, subject)

        async def reply(text: str, _to: str = from_addr, _subj: str = subject) -> None:
            await asyncio.to_thread(_send_reply_sync, _to, f"Re: {_subj}", text)

        event = NormalizedEvent(user_id=from_addr, channel=Channel.EMAIL, text=body, reply=reply)
        async with session_scope() as session:
            await dispatch_event(session, event)


async def run_email_adapter() -> None:
    """Runs until cancelled — polls IMAP every POLL_INTERVAL_SECONDS."""
    tag = get_settings().email_trigger_tag
    if not _tag_is_usable(tag):
        logger.error(
            "Email adapter NOT started: EMAIL_TRIGGER_TAG %r is empty or not plain ASCII "
            "without quotes/backslashes. The mailbox is shared with ordinary mail, so the "
            "adapter refuses to run without a usable tag.",
            tag,
        )
        return
    folder = get_settings().email_agent_folder
    logger.info(
        "Email adapter started (polling every %ss, only subjects containing %r, "
        "handled mail filed into %s).",
        POLL_INTERVAL_SECONDS,
        tag,
        repr(folder) if folder.strip() else "nowhere (stays in INBOX)",
    )
    while True:
        try:
            await _poll_once()
        except Exception:
            logger.exception("Email poll failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
