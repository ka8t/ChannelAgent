"""Fresh end-to-end verification of closed issues, against a throwaway DB
and a mock LLM. Never touches the real .env values that matter or data/."""

import asyncio
import os
import sqlite3
import subprocess
import sys
import tempfile

from cryptography.fernet import Fernet

TMP = tempfile.mkdtemp(prefix="ca_verify_")
DB = f"{TMP}/v.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB}"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["API_SERVER_KEY"] = "k" * 32
os.environ["TELEGRAM_ALLOWED_USERS"] = "111"
os.environ["LLAMA_SERVER_URL"] = "http://127.0.0.1:18999"

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((bool(cond), name))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


async def main() -> None:
    import httpx
    import uvicorn
    from fastapi import FastAPI, Request
    from sqlalchemy import func, select

    # --- mock LLM: replies with how many messages it received ---
    mock = FastAPI()

    @mock.post("/v1/chat/completions")
    async def chat(req: Request):
        body = await req.json()
        n = len(body["messages"])
        return {"choices": [{"message": {"content": f"N={n}"}}]}

    server = uvicorn.Server(uvicorn.Config(mock, port=18999, log_level="error"))
    task = asyncio.create_task(server.serve())
    for _ in range(50):
        if server.started:
            break
        await asyncio.sleep(0.1)

    from app.admin import service
    from app.api.app import app as api_app
    from app.channels.dispatch import DENIED_MESSAGE, dispatch_event
    from app.channels.schema import NormalizedEvent
    from app.config import get_settings
    from app.db.bootstrap import bootstrap_admin_from_env
    from app.db.models import (
        AccessRequest, ActionLog, Channel, ChannelIdentity, Direction, User,
    )
    from app.db.session import init_db, session_scope
    from app.graph import build_thread_id, run_turn
    from app.security.auth import authorize
    from app.security.hashing import channel_identifier_key

    # ---- #10/#11: migrations from an empty file ----
    await init_db()
    con = sqlite3.connect(DB)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    expected = {"users", "channel_identities", "permissions", "agents", "action_logs",
                "access_requests", "alembic_version"}
    check("#10/#11 fresh DB has all 7 tables", expected <= tables, f"missing={expected - tables}")
    ver = con.execute("select version_num from alembic_version").fetchall()
    check("#11 alembic_version has exactly 1 row", len(ver) == 1, f"rows={len(ver)} ver={ver}")
    con.close()
    chk = subprocess.run([sys.executable, "-m", "alembic", "check"], capture_output=True,
                         text=True, env=os.environ)
    check("#11 alembic check: models == migrations", chk.returncode == 0,
          f"exit={chk.returncode} {chk.stdout.strip()[-80:]}{chk.stderr.strip()[-120:]}")

    # ---- #14: bootstrap idempotent + env never read again ----
    async with session_scope() as s:
        await bootstrap_admin_from_env(s)
        await bootstrap_admin_from_env(s)
        n = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        check("#14 bootstrap twice -> 1 user", n == 1, f"users={n}")
        d = await authorize(s, Channel.TELEGRAM, "111")
        check("#14/#12 bootstrap admin allowed+is_admin", d.allowed and d.is_admin,
              f"allowed={d.allowed} admin={d.is_admin}")
    os.environ["TELEGRAM_ALLOWED_USERS"] = "222"
    get_settings.cache_clear()
    async with session_scope() as s:
        await bootstrap_admin_from_env(s)
        n = (await s.execute(select(func.count()).select_from(User))).scalar_one()
        d = await authorize(s, Channel.TELEGRAM, "222")
        check("#14 env changed later -> ignored (users still 1, 222 denied)",
              n == 1 and not d.allowed, f"users={n} allowed222={d.allowed}")

    # ---- #22/#25: API auth, incl. FastAPI's own doc routes ----
    key = {"Authorization": "Bearer " + "k" * 32}
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        for path in ["/users", "/docs", "/redoc", "/openapi.json"]:
            r = await c.get(path)
            check(f"#22/#25 GET {path} no key -> not 200", r.status_code in (401, 404),
                  f"status={r.status_code}")
        r = await c.get("/users", headers={"Authorization": "Bearer wrong"})
        check("#22 wrong key -> 401", r.status_code == 401, f"status={r.status_code}")
        for path in ["/users", "/docs", "/openapi.json"]:
            r = await c.get(path, headers=key)
            check(f"#22/#25 GET {path} real key -> 200", r.status_code == 200,
                  f"status={r.status_code}")

        # ---- #23/#24: CRUD + grant/revoke, cross-checked with authorize() ----
        r = await c.post("/users", json={"display_name": "Mail user"}, headers=key)
        uid = r.json()["id"]
        check("#23 POST /users -> 201", r.status_code == 201, f"status={r.status_code} id={uid}")
        addr = "Secret.Person@example.com"
        r = await c.post(f"/users/{uid}/channels", headers=key,
                         json={"channel": "email", "identifier": addr})
        cid = r.json()["id"]
        check("#23 POST email identity -> 201", r.status_code == 201, f"status={r.status_code}")
        check("#9 API response leaks no address / raw_address",
              addr.lower() not in r.text.lower() and "raw_address" not in r.text,
              f"body={r.text[:100]}")
        r = await c.post(f"/users/{uid}/channels", headers=key,
                         json={"channel": "email", "identifier": addr})
        check("#23 duplicate identity -> 409", r.status_code == 409, f"status={r.status_code}")

        async with session_scope() as s:
            d = await authorize(s, Channel.EMAIL, addr)
        check("#12 identity w/o permission -> denied", not d.allowed, f"allowed={d.allowed}")
        r = await c.post(f"/users/{uid}/channels/{cid}/permissions", headers=key,
                         json={"kind": "chat"})
        check("#24 grant chat -> 201", r.status_code == 201, f"status={r.status_code}")
        async with session_scope() as s:
            d = await authorize(s, Channel.EMAIL, addr)
        check("#24 API grant visible to authorize() -> allowed", d.allowed, f"allowed={d.allowed}")
        check("#13 chat perm is not admin", not d.is_admin, f"admin={d.is_admin}")

        # raw DB inspection: encryption at rest
        con = sqlite3.connect(DB)
        raw, ext = con.execute(
            "select raw_address, external_id from channel_identities where id=?", (cid,)
        ).fetchone()
        con.close()
        check("#9 raw_address encrypted at rest (Fernet token, no plaintext)",
              raw is not None and raw.startswith("gAAAA") and "example.com" not in raw,
              f"raw[:12]={raw[:12] if raw else None}")
        check("#8 external_id is a hash, not the address",
              "example.com" not in ext and ext == channel_identifier_key(Channel.EMAIL, addr),
              f"ext[:12]={ext[:12]}")

        r = await c.delete(f"/users/{uid}/channels/{cid}/permissions/chat", headers=key)
        check("#24 revoke -> 204", r.status_code == 204, f"status={r.status_code}")
        async with session_scope() as s:
            d = await authorize(s, Channel.EMAIL, addr)
        check("#24 API revoke immediately denies", not d.allowed, f"allowed={d.allowed}")
        r = await c.delete(f"/users/{uid}/channels/{cid}/permissions/chat", headers=key)
        check("#24 revoke twice -> 404", r.status_code == 404, f"status={r.status_code}")

        await c.post(f"/users/{uid}/channels/{cid}/permissions", headers=key,
                     json={"kind": "chat"})
        await c.patch(f"/users/{uid}", json={"is_active": False}, headers=key)
        async with session_scope() as s:
            d = await authorize(s, Channel.EMAIL, addr)
        check("#12 inactive user with permission -> denied", not d.allowed, f"allowed={d.allowed}")
        r = await c.delete(f"/users/{uid}", headers=key)
        check("#23 DELETE user -> 204", r.status_code == 204, f"status={r.status_code}")
        async with session_scope() as s:
            n = (await s.execute(
                select(func.count()).select_from(ChannelIdentity).where(ChannelIdentity.id == cid)
            )).scalar_one()
        check("#23 delete cascades to identity", n == 0, f"identity rows={n}")

    # ---- #16/#15/#37: graph, history accumulation, isolation, thread ids ----
    t_email = build_thread_id(Channel.EMAIL, addr, 4)
    check("#16 email thread_id has no raw address",
          "example.com" not in t_email and t_email.startswith("email_") and t_email.endswith("_4"),
          f"thread={t_email[:20]}...")
    check("#37 thread_id differs per agent",
          build_thread_id(Channel.TELEGRAM, "5", 1) != build_thread_id(Channel.TELEGRAM, "5", 2),
          "")
    r1 = await run_turn(Channel.TELEGRAM, "5", 1, "a")
    r2 = await run_turn(Channel.TELEGRAM, "5", 1, "b")
    r3 = await run_turn(Channel.TELEGRAM, "5", 1, "c")
    check("#15/#16 history accumulates (N=1,3,5)", (r1, r2, r3) == ("N=1", "N=3", "N=5"),
          f"{r1},{r2},{r3}")
    ro = await run_turn(Channel.TELEGRAM, "6", 1, "x")
    ra = await run_turn(Channel.TELEGRAM, "5", 2, "x")
    check("#16/#37 other user / other agent start fresh (N=1,N=1)", (ro, ra) == ("N=1", "N=1"),
          f"{ro},{ra}")

    # ---- #17/#36/#38/#37: dispatch pipeline ----
    sent: list[str] = []

    async def reply(t: str) -> None:
        sent.append(t)

    # unknown identity -> AccessRequest, denial message, no ActionLog
    async with session_scope() as s:
        await dispatch_event(s, NormalizedEvent("999", Channel.TELEGRAM, "let me in", reply))
    async with session_scope() as s:
        reqs = (await s.execute(select(AccessRequest))).scalars().all()
        logs = (await s.execute(select(func.count()).select_from(ActionLog))).scalar_one()
    check("#36 unknown identity -> 1 pending request, 0 action logs, denial sent",
          len(reqs) == 1 and logs == 0 and sent[-1] == DENIED_MESSAGE,
          f"requests={len(reqs)} logs={logs} status={reqs[0].status if reqs else None}")
    async with session_scope() as s:
        await dispatch_event(s, NormalizedEvent("999", Channel.TELEGRAM, "again", reply))
        n = (await s.execute(select(func.count()).select_from(AccessRequest))).scalar_one()
    check("#36 second message from same identity -> still 1 request (upsert)", n == 1,
          f"requests={n}")

    # approve -> user can now chat
    async with session_scope() as s:
        pending = await service.list_pending_requests(s)
        user = await service.approve_request(s, pending[0].id)
        await s.commit()
        uid999 = user.id
    async with session_scope() as s:
        d = await authorize(s, Channel.TELEGRAM, "999")
    check("#36 approve -> identity authorized", d.allowed, f"allowed={d.allowed}")
    async with session_scope() as s:
        await dispatch_event(s, NormalizedEvent("999", Channel.TELEGRAM, "hello", reply))
    check("#17 authorized event -> LLM reply delivered via reply()", sent[-1] == "N=1",
          f"reply={sent[-1]}")

    marker = "TOP-SECRET-MARKER-12345"
    async with session_scope() as s:
        await dispatch_event(s, NormalizedEvent("999", Channel.TELEGRAM, marker, reply))
    con = sqlite3.connect(DB)
    rows = con.execute(
        "select direction, text from action_logs where user_id=? order by id", (uid999,)
    ).fetchall()
    con.close()
    dirs = [r[0].lower() for r in rows]
    check("#38 4 action_logs (in,out,in,out) for that user",
          dirs == ["inbound", "outbound", "inbound", "outbound"], f"dirs={dirs}")
    check("#38 ActionLog text encrypted at rest (marker absent in raw DB)",
          all(marker not in r[1] and r[1].startswith("gAAAA") for r in rows), "")
    async with session_scope() as s:
        logs = (await s.execute(select(ActionLog).where(ActionLog.user_id == uid999))).scalars()
        texts = [e.text for e in logs]
    check("#38 ORM decrypts transparently", marker in texts, f"n={len(texts)}")

    # deny path + agents (admin edit)
    async with session_scope() as s:
        req = await service.request_access(s, Channel.TELEGRAM, "777", "hi")
        await service.deny_request(s, req.id)
        await s.commit()
        d = await authorize(s, Channel.TELEGRAM, "777")
    check("#36 deny -> stays unauthorized", not d.allowed, f"allowed={d.allowed}")
    async with session_scope() as s:
        a1 = await service.get_or_create_default_agent(s, uid999)
        a1b = await service.get_or_create_default_agent(s, uid999)
        a2 = await service.create_agent(s, uid999, "second")
        await service.rename_agent(s, a2.id, "renamed")
        await service.set_agent_active(s, a2.id, False)
        await s.commit()
        agents = await service.list_agents(s, uid999)
    check("#37 default agent lazy+stable; 2nd agent renamed+deactivated",
          a1.id == a1b.id and len(agents) == 2
          and any(a.name == "renamed" and not a.is_active for a in agents),
          f"agents={[(a.name, a.is_active) for a in agents]}")

    server.should_exit = True
    await task
    from app.graph import close_graph
    await close_graph()

    ok = sum(1 for r in results if r[0])
    print(f"\nTOTAL: {ok} passed, {len(results) - ok} failed, {len(results)} checks")
    sys.exit(0 if ok == len(results) else 1)


asyncio.run(main())
