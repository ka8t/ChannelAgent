"""Supervised live run, ONLY the email adapter, instrumented: every IMAP
UID command, LIST, CREATE, SUBSCRIBE and EXPUNGE is logged (never
credentials). Logging is re-enabled after init_db() because
alembic/env.py's fileConfig() disables the app's loggers (issue #45).
App code is not changed here. Stops itself after 15 minutes."""
import asyncio
import imaplib
import logging
import os

os.environ["LLAMA_SERVER_URL"] = "http://localhost:8080"

import app.channels.email as em  # noqa: E402
from app.db.session import init_db  # noqa: E402

audit = logging.getLogger("liveaudit")


class LoggedIMAP(imaplib.IMAP4_SSL):
    def uid(self, command, *args):
        r = super().uid(command, *args)
        detail = r[1] if command.upper() == "SEARCH" else r[0]
        audit.info("IMAP UID %s %s -> %s", command, args, detail)
        return r

    def list(self, *a, **k):
        r = super().list(*a, **k)
        audit.info("IMAP LIST %s -> %s", k or a, r[0])
        return r

    def create(self, mailbox):
        r = super().create(mailbox)
        audit.info("IMAP CREATE %s -> %s", mailbox, r[0])
        return r

    def subscribe(self, mailbox):
        r = super().subscribe(mailbox)
        audit.info("IMAP SUBSCRIBE %s -> %s", mailbox, r[0])
        return r

    def expunge(self):
        audit.info("IMAP plain EXPUNGE (must never happen)")
        return super().expunge()


em.imaplib.IMAP4_SSL = LoggedIMAP


async def main() -> None:
    await init_db()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", force=True)
    for name in ("channelagent", "httpx", "liveaudit"):
        logging.getLogger(name).disabled = False
        logging.getLogger(name).setLevel(logging.INFO)
    try:
        await asyncio.wait_for(em.run_email_adapter(), timeout=900)
    except TimeoutError:
        logging.getLogger("channelagent").info("Live test window over (15 min), stopping.")

asyncio.run(main())
