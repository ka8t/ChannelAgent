"""Interactive admin console (#41): ./start.sh --admin.

Every action here calls the same app.admin.service functions a future
Admin API endpoint for these entities would (#35's one-service-layer
principle) — this file is a menu over existing business logic, it
must not grow new logic of its own.
"""

import asyncio

from sqlalchemy import select

from app.admin import service
from app.db.models import ActionLog, User
from app.db.session import init_db, session_scope


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


async def _menu_requests() -> None:
    async with session_scope() as session:
        pending = await service.list_pending_requests(session)
        if not pending:
            print("No pending requests.")
            return
        for r in pending:
            print(f"  [{r.id}] {r.channel.value}/{r.external_id} -- \"{r.first_message_text}\"")
        choice = _prompt("Request id to resolve (blank to go back)")
        if not choice:
            return
        action = _prompt("approve/deny")
        if action == "approve":
            user = await service.approve_request(session, int(choice))
            await session.commit()
            print(f"Approved. Created user id={user.id}.")
        elif action == "deny":
            await service.deny_request(session, int(choice))
            await session.commit()
            print("Denied.")
        else:
            print("Unknown action, nothing changed.")


async def _menu_users() -> None:
    async with session_scope() as session:
        users = list((await session.execute(select(User))).scalars().all())
        for u in users:
            status = "active" if u.is_active else "inactive"
            print(f"  [{u.id}] {u.display_name or '(no name)'} ({status})")
        choice = _prompt("User id to deactivate (blank to go back)")
        if not choice:
            return
        user = await session.get(User, int(choice))
        if user is None:
            print("No such user.")
            return
        user.is_active = False
        await session.commit()
        print(f"Deactivated user {user.id}.")


async def _menu_agents() -> None:
    choice = _prompt("User id (blank to go back)")
    if not choice:
        return
    user_id = int(choice)
    async with session_scope() as session:
        agents = await service.list_agents(session, user_id)
        for a in agents:
            status = "active" if a.is_active else "inactive"
            print(f"  [{a.id}] {a.name} ({status})")
        action = _prompt("create/rename/deactivate (blank to go back)")
        if action == "create":
            name = _prompt("New agent name")
            agent = await service.create_agent(session, user_id, name)
            await session.commit()
            print(f"Created agent id={agent.id}.")
        elif action == "rename":
            agent_id = int(_prompt("Agent id"))
            new_name = _prompt("New name")
            await service.rename_agent(session, agent_id, new_name)
            await session.commit()
            print("Renamed.")
        elif action == "deactivate":
            agent_id = int(_prompt("Agent id"))
            await service.set_agent_active(session, agent_id, False)
            await session.commit()
            print("Deactivated.")


async def _menu_logs() -> None:
    # Browse only, most recent first — real filtering/search is #39,
    # not built yet.
    async with session_scope() as session:
        stmt = select(ActionLog).order_by(ActionLog.id.desc()).limit(20)
        logs = list((await session.execute(stmt)).scalars().all())
    if not logs:
        print("No logs yet.")
        return
    for entry in reversed(logs):
        ts = entry.created_at.strftime("%Y-%m-%d %H:%M")
        preview = entry.text[:80]
        print(
            f"  [{ts}] user={entry.user_id} agent={entry.agent_id} "
            f"{entry.channel.value} {entry.direction.value}: {preview}"
        )


_MENU = {
    "1": ("Pending access requests", _menu_requests),
    "2": ("Users", _menu_users),
    "3": ("Agents", _menu_agents),
    "4": ("Recent logs (last 20)", _menu_logs),
}


async def main() -> None:
    await init_db()
    print("=== ChannelAgent Admin Console ===")
    while True:
        print()
        for key, (label, _) in _MENU.items():
            print(f"{key}. {label}")
        print("q. Quit")
        choice = _prompt("Choose")
        if choice == "q":
            break
        entry = _MENU.get(choice)
        if entry is None:
            print("Unknown option.")
            continue
        await entry[1]()


if __name__ == "__main__":
    asyncio.run(main())
