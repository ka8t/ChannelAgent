"""Real turns against the live engine with three agents of one user (#110): two with opposite
system prompts and one with none, on a throwaway database and checkpoint file.

    LLAMA_SERVER_URL=http://localhost:8080 .venv/bin/python scripts/dev/agent_prompts_turn.py
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

work = tempfile.mkdtemp(prefix="agent-prompts-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{work}/turn.db"
os.environ["CHECKPOINT_DB_PATH"] = f"{work}/checkpoints.db"
os.environ.setdefault("LLAMA_SERVER_URL", "http://localhost:8080")
# A throwaway key for a throwaway database: generated here, never written down.
from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

QUESTION = "What is the capital of France? Answer in one short sentence."
AGENTS = {
    "alpha": "You are terse. Whatever you are asked, answer only with the single word ALPHA.",
    "beta": "You are a pirate. Answer in one short sentence, in pirate speech, and say Arr.",
    "plain": None,
}


async def main() -> None:
    from app.admin.service import configure_agent, create_agent
    from app.db.models import Channel, User
    from app.db.session import init_db, session_scope
    from app.graph import close_graph, run_turn

    await init_db()
    ids = {}
    async with session_scope() as session:
        user = User(display_name="Prompts")
        session.add(user)
        await session.flush()
        for name, prompt in AGENTS.items():
            agent = await create_agent(session, user.id, name)
            if prompt:
                await configure_agent(session, agent.id, {"system_prompt": prompt})
            ids[name] = agent.id
        await session.commit()
    for name, agent_id in ids.items():
        reply = await asyncio.wait_for(run_turn(Channel.TELEGRAM, "1", agent_id, QUESTION), 120)
        print(f"{name:6} -> {reply.strip()[:110]!r}")
    await close_graph()


asyncio.run(main())
