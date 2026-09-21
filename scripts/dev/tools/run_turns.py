import asyncio, os, sys, tempfile
os.environ["LLAMA_SERVER_URL"] = "http://127.0.0.1:18998"
# A turn reads its agent's settings from the database (#110): a throwaway one, shared by the
# processes of one demonstration, never the real data/.
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.gettempdir()}/run_turns.db")
from app.db.models import Channel
from app.db.session import init_db
from app.graph import run_turn
async def main():
    n = int(sys.argv[1])
    await init_db()
    for i in range(n): r = await run_turn(Channel.TELEGRAM, "42", 1, f"msg {i}")
    print(f"process ran {n} turn(s); last reply = {r}")
asyncio.run(main())
