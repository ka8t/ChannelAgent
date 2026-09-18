"""ChannelAgent entrypoint.

Currently brings up configuration and the database, which is enough to
prove the application boots correctly inside the container (fails fast
on a missing ENCRYPTION_KEY, creates DB tables on first run). Channel
adapters (Telegram/Email/Matrix — see epic #6 on the issue tracker)
will be wired in here once they exist; there is nothing to route
messages through yet.
"""

import asyncio
import logging

from app.config import get_settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("channelagent")


async def main() -> None:
    settings = get_settings()
    await init_db()
    logger.info("ChannelAgent started. LLM gateway: %s", settings.llama_server_url)
    logger.info("No channel adapters are wired in yet (see epic #6 on the issue tracker).")
    # Keeps the process alive instead of exiting immediately — replaced by
    # real adapter event loops (Telegram polling, IMAP polling, Matrix
    # sync) once they exist.
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
