import asyncio, os, sqlite3
import httpx
from app.api.app import app
from app.channels import dispatch
from app.channels.schema import NormalizedEvent
from app.config import get_settings
from app.db.models import Channel
from app.db.session import init_db, session_scope
DB = os.environ["DATABASE_URL"].split("///")[1]
sql = lambda q: sqlite3.connect(DB).execute(q).fetchall()
async def main():
    await init_db()
    print("migrated copy, identities:", sql("select id, channel, active_agent_id from channel_identities"), "| agents:", sql("select id, user_id, name from agents"))
    H = {"Authorization": f"Bearer {get_settings().api_server_key}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/users/2/agents", json={"name": "work"}, headers=H); print("POST agent 'work' for user 2 ->", r.status_code, r.json()["id"])
        r = await c.put("/users/2/channels/2/agent", json={"agent_id": 3}, headers=H); print("PUT identity 2 -> agent 3     ->", r.status_code, r.json())
        r = await c.put("/users/2/channels/2/agent", json={"agent_id": 1}, headers=H); print("PUT another user's agent 1    ->", r.status_code, r.json()["detail"])
    seen = []
    async def fake(channel, user, agent_id, text): seen.append(agent_id); return "ok"
    dispatch.run_turn = fake
    replies = []
    async def reply(t): replies.append(t)
    async with session_scope() as s:
        out = await dispatch.dispatch_event(s, NormalizedEvent("montezuma@outlook.fr", Channel.EMAIL, "hello", reply))
    print("email from montezuma@outlook.fr ->", out.value, "| agent that answered:", seen, "| log agent ids:", sql("select agent_id, direction from action_logs where id > 8"))
asyncio.run(main())
