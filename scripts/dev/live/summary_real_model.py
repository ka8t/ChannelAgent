"""#86/#87 against the real llama-server on localhost:8080 (throwaway database and
checkpoints in a temp directory): exact token counts from the real /tokenize, then a
long conversation with a small context window; a fact given in the first message must
still be answered at the end thanks to the running summary.

Usage: PYTHONPATH=. .venv/bin/python scripts/dev/live/summary_real_model.py
"""
from cryptography.fernet import Fernet
import asyncio
import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{tmp}/t.db",
    CHECKPOINT_DB_PATH=f"{tmp}/c.db",
    ENCRYPTION_KEY=Fernet.generate_key().decode(),
    LLAMA_SERVER_URL="http://localhost:8080",
    LLAMA_CTX_SIZE="700",
)
import httpx  # noqa: E402

from app import graph  # noqa: E402
from app.db.models import Channel  # noqa: E402

FILLER = "Parle-moi en une phrase courte d'un sujet quelconque numero {i}."


async def main():
    r = httpx.post("http://localhost:8080/tokenize", json={"content": "Bonjour tout le monde"})
    print("real /tokenize on 'Bonjour tout le monde':", len(r.json()["tokens"]), "tokens")
    await graph.run_turn(Channel.TELEGRAM, "1", 1, "Retiens ceci: mon numero de dossier est 4711.")
    for i in range(1, 25):
        await graph.run_turn(Channel.TELEGRAM, "1", 1, FILLER.format(i=i))
    answer = await graph.run_turn(Channel.TELEGRAM, "1", 1, "Quel est mon numero de dossier ?")
    compiled = await graph.get_graph()
    state = (await compiled.aget_state(
        {"configurable": {"thread_id": graph.build_thread_id(Channel.TELEGRAM, "1", 1)}})).values
    print("messages stored:", len(state["messages"]), "| summary covers:", state.get("summary_covers"))
    print("summary:", state.get("summary", "")[:200].replace("\n", " "))
    print("final answer:", answer[:200].replace("\n", " "))
    print("4711 in the answer:", "4711" in answer)
    await graph.close_graph()


asyncio.run(main())
