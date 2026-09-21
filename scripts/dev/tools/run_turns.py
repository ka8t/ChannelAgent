import asyncio, os, sys
os.environ["LLAMA_SERVER_URL"] = "http://127.0.0.1:18998"
from app.db.models import Channel
from app.graph import run_turn
async def main():
    n = int(sys.argv[1])
    for i in range(n): r = await run_turn(Channel.TELEGRAM, "42", 1, f"msg {i}")
    print(f"process ran {n} turn(s); last reply = {r}")
asyncio.run(main())
