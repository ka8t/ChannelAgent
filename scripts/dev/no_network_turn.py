"""One real chat turn against the live engine, with every connection outside this machine
refused and counted (#138). Prints the HTTP status of the completion call, the connections
made to this machine and the attempts to go anywhere else (expected: none).

    LLAMA_SERVER_URL=http://localhost:8080 .venv/bin/python scripts/dev/no_network_turn.py

It runs on a throwaway database and checkpoint file, never on the real data.
"""

import asyncio
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

work = tempfile.mkdtemp(prefix="no-network-turn-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{work}/turn.db"
os.environ["CHECKPOINT_DB_PATH"] = f"{work}/checkpoints.db"
os.environ.setdefault("LLAMA_SERVER_URL", "http://localhost:8080")
os.environ.setdefault("ENCRYPTION_KEY", "PmKTledxEc-gdO4tty5QO4PjB48zp_GqWMVIpigdwEg=")

local, outside, statuses = [], [], []
real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo


def is_local(host) -> bool:
    """This machine: loopback names and addresses, including the address `localhost` gets on
    the loopback interface (`fe80::1%lo0` on macOS)."""
    # asyncio hands the name over as bytes
    host = host.decode() if isinstance(host, bytes) else str(host)
    zone = host.partition("%")[2]
    return (
        host in ("127.0.0.1", "::1", "localhost", "")
        or host.startswith("127.")
        or zone.startswith("lo")
    )


def connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if self.family == socket.AF_UNIX or is_local(host):
        local.append(address)
        return real_connect(self, address)
    outside.append(("connect", address))
    raise OSError("blocked")


def getaddrinfo(host, *args, **kwargs):
    if host is not None and not is_local(host):
        outside.append(("lookup", host))
        raise socket.gaierror("blocked")
    return real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect, socket.getaddrinfo = connect, getaddrinfo


async def main() -> int:
    import httpx

    original = httpx.AsyncClient.send

    async def recording(self, request, **kwargs):
        response = await original(self, request, **kwargs)
        if request.url.path.endswith("/chat/completions"):
            statuses.append(response.status_code)
        return response

    httpx.AsyncClient.send = recording
    from app.admin.service import create_agent
    from app.db.models import Channel, User
    from app.db.session import init_db, session_scope
    from app.graph import close_graph, run_turn

    await init_db()
    async with session_scope() as session:
        user = User(display_name="No network")
        session.add(user)
        await session.flush()
        agent = await create_agent(session, user.id, "default")
        await session.commit()
        agent_id = agent.id
    try:
        reply = await asyncio.wait_for(
            run_turn(Channel.TELEGRAM, "1", agent_id, "Reply with the single word: ok"), 60
        )
    except Exception as exc:  # noqa: BLE001 - report what was refused, then fail
        print(f"the turn failed: {type(exc).__name__}; refused so far: {outside}")
        return 1
    await close_graph()
    print(f"reply: {reply!r}")
    print(f"HTTP status of the completion call(s): {statuses}")
    print(f"connections to this machine: {len(local)}")
    print(f"connections or lookups outside this machine: {len(outside)} {outside}")
    return 0 if statuses == [200] and not outside else 1


sys.exit(asyncio.run(asyncio.wait_for(main(), timeout=120)))
