"""#90: the real application with a real email adapter stuck on an IMAP server that
accepts connections and never answers. Prints, second by second, what the healthcheck
reads. Limits are shortened (poll 1 s, max age 6 s, heartbeat 1 s); the logic is the
production one. Throwaway database in a temp directory.

Usage: PYTHONPATH=. .venv/bin/python scripts/dev/live/stuck_adapter_demo.py
"""
from cryptography.fernet import Fernet
import asyncio
import os
import socket
import tempfile
import threading
import time

tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{tmp}/t.db",
    CHECKPOINT_DB_PATH=f"{tmp}/c.db",
    ENCRYPTION_KEY=Fernet.generate_key().decode(),
    TELEGRAM_BOT_TOKEN="",
    API_SERVER_KEY="",
    MIGRATION_BACKUPS_KEEP="0",
    EMAIL_USERNAME="u@example.org",
    EMAIL_PASSWORD="not-used",
)
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(5)
os.environ["EMAIL_IMAP_HOST"] = "127.0.0.1"
os.environ["EMAIL_IMAP_PORT"] = str(server.getsockname()[1])
held = []
threading.Thread(target=lambda: [held.append(server.accept()) for _ in iter(int, 1)], daemon=True).start()

from pathlib import Path  # noqa: E402

from app import health, main as app_main  # noqa: E402
from app.channels import email as email_adapter  # noqa: E402

health.HEARTBEAT_PATH = Path(tmp) / "beat"
health.heartbeat.__defaults__ = (1,)  # beat every second instead of every 15
email_adapter.POLL_INTERVAL_SECONDS = 1
email_adapter.LIVENESS_MAX_AGE_SECONDS = 6
# The email adapter needs a usable tag; the stub server never lets it get further.


async def main():
    from app.db.session import init_db

    await init_db()
    task = asyncio.create_task(app_main.main())
    start = time.time()
    last = None
    while time.time() - start < 20:
        await asyncio.sleep(1)
        ok, msg = health.check(max_age=3)
        state = "healthy" if ok else "UNHEALTHY"
        if state != last:
            print(f"t+{time.time() - start:4.1f}s  {state:9}  ({msg}) | connections held by the stub IMAP: {len(held)}")
            last = state
    task.cancel()


asyncio.run(main())
