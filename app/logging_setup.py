"""No secret reaches a log (#82).

The Telegram bot token is part of every Bot API URL (`/bot<token>/getMe`) and
httpx logs the URL of each request at INFO: with the adapter running, the
complete token was written to the terminal and to `docker logs`, one line per
poll. Two layers:

1. `httpx` and `httpcore` do not log at INFO (their line adds nothing the
   adapter's own lines do not say);
2. every log record is scrubbed **when it is created**, whatever logger emits it
   and whatever handler prints it (uvicorn rebuilds its own handlers when it
   starts, so a filter on handlers would not hold): anything shaped like a
   Telegram token, and the literal value of every configured secret, becomes
   `<redacted>` in the message, its arguments, the traceback and the stack.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import traceback

REDACTED = "<redacted>"
MIN_SECRET_LENGTH = 8  # a shorter value would redact ordinary words
_TELEGRAM_TOKEN = re.compile(r"[0-9]{5,}:[A-Za-z0-9_-]{20,}")

_secrets: tuple[str, ...] = ()


def configured_secrets() -> list[str]:
    """The literal values that must never be printed: the configured secrets and
    the old key a rotation is given through the environment.
    """
    from app.config import get_settings

    settings = get_settings()
    values = [
        settings.telegram_bot_token,
        settings.api_server_key,
        settings.encryption_key,
        settings.email_password,
        settings.matrix_bot_access_token,
        os.environ.get("OLD_ENCRYPTION_KEY"),
    ]
    return [v for v in values if v and len(v) >= MIN_SECRET_LENGTH]


def scrub(text: str) -> str:
    for secret in _secrets:
        text = text.replace(secret, REDACTED)
    return _TELEGRAM_TOKEN.sub(REDACTED, text)


def _scrub_record(record: logging.LogRecord) -> None:
    message = record.getMessage()  # may raise on a bad format: the caller leaves the record alone
    record.msg = scrub(message)
    record.args = None
    if record.exc_info and not record.exc_text:
        record.exc_text = scrub(logging.Formatter().formatException(record.exc_info))
    if record.stack_info:
        record.stack_info = scrub(record.stack_info)


def install_redaction(secrets: list[str] | None = None) -> None:
    """Scrub every record from now on. `secrets` defaults to the configured ones.
    Calling it again only updates the list of secrets.
    """
    global _secrets
    if secrets is None:
        try:
            secrets = configured_secrets()
        except Exception:  # settings that cannot load are reported by the app itself
            secrets = []
    _secrets = tuple(
        sorted({s for s in secrets if s and len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True)
    )
    current = logging.getLogRecordFactory()
    if getattr(current, "_redacting", False):
        return

    def factory(*args, **kwargs) -> logging.LogRecord:
        record = current(*args, **kwargs)
        try:
            _scrub_record(record)
        except Exception:  # logging must never break the caller
            pass
        return record

    factory._redacting = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)
    _install_excepthooks()


def _install_excepthooks() -> None:
    """An uncaught exception is printed by the interpreter, not by logging: an
    invalid Telegram token made the app end with `The token <token> was rejected
    by the server` in a raw traceback. Print those scrubbed too.
    """
    if not getattr(sys.excepthook, "_redacting", False):
        previous = sys.excepthook

        def hook(exc_type, exc, tb) -> None:
            try:
                sys.stderr.write(scrub("".join(traceback.format_exception(exc_type, exc, tb))))
            except Exception:
                previous(exc_type, exc, tb)

        hook._redacting = True  # type: ignore[attr-defined]
        sys.excepthook = hook
    if not getattr(threading.excepthook, "_redacting", False):
        previous_thread = threading.excepthook

        def thread_hook(args) -> None:
            try:
                text = "".join(
                    traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                )
                sys.stderr.write(f"Exception in thread {getattr(args.thread, 'name', '?')}:\n")
                sys.stderr.write(scrub(text))
            except Exception:
                previous_thread(args)

        thread_hook._redacting = True  # type: ignore[attr-defined]
        threading.excepthook = thread_hook


def configure_logging(level: int = logging.INFO) -> None:
    """The logging setup of the long-running application (`app/main.py`)."""
    logging.basicConfig(level=level)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    install_redaction()
