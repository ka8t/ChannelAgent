"""Interactive admin console (#41): ./start.sh --admin.

Every action here calls the same app.admin.service functions a future
Admin API endpoint for these entities would (#35's one-service-layer
principle) — this file is a menu over existing business logic, it
must not grow new logic of its own.
"""

import asyncio
import enum
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.admin import service
from app.db.models import Channel, Direction, User
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


_DEFAULT_LOG_LIMIT = 20


class _BadInput(Exception):
    """A prompt answer that cannot be used. Printed, never a traceback."""


def _ask_optional(label: str, parse: Callable[[str], object], hint: str) -> object | None:
    raw = _prompt(label)
    if not raw:
        return None
    try:
        return parse(raw)
    except ValueError as exc:
        raise _BadInput(f"{label}: {hint}") from exc


def _ask_enum(label: str, enum_cls: type[enum.StrEnum]) -> object | None:
    choices = "/".join(e.value for e in enum_cls)
    return _ask_optional(
        f"{label} ({choices}, blank = any)", lambda raw: enum_cls(raw.lower()), choices
    )


def _ask_day(label: str, *, inclusive_end: bool = False) -> datetime | None:
    def parse(raw: str) -> datetime:
        day = date.fromisoformat(raw)
        moment = datetime(day.year, day.month, day.day, tzinfo=UTC)
        # A bare "to" date means that whole day, so the exclusive upper
        # bound handed to the service is the start of the next day.
        return moment + timedelta(days=1) if inclusive_end else moment

    return _ask_optional(f"{label} (YYYY-MM-DD, UTC, blank = any)", parse, "expected YYYY-MM-DD")


async def _menu_logs() -> None:
    """Search the audit trail through service.search_action_logs (#39),
    the same function GET /logs uses. Blank answers mean "no filter".
    """
    try:
        user_id = _ask_optional("User id (blank = any)", int, "expected a number")
        agent_id = _ask_optional("Agent id (blank = any)", int, "expected a number")
        channel = _ask_enum("Channel", Channel)
        direction = _ask_enum("Direction", Direction)
        since = _ask_day("From date")
        until = _ask_day("To date, inclusive", inclusive_end=True)
        keyword = _prompt("Keyword in the message text (blank = any)") or None
        asked_limit = _ask_optional("Max results (blank = 20)", int, "expected a number")
        limit = _DEFAULT_LOG_LIMIT if asked_limit is None else asked_limit
    except _BadInput as exc:
        print(f"Invalid input, nothing searched. {exc}")
        return

    async with session_scope() as session:
        try:
            logs = await service.search_action_logs(
                session,
                user_id=user_id,
                agent_id=agent_id,
                channel=channel,
                direction=direction,
                since=since,
                until=until,
                keyword=keyword,
                limit=limit,
            )
        except ValueError as exc:
            print(f"Invalid input, nothing searched. {exc}")
            return
    if not logs:
        print("No matching logs.")
        return
    print(f"{len(logs)} result(s), most recent first:")
    for entry in logs:
        ts = entry.created_at.strftime("%Y-%m-%d %H:%M")
        preview = entry.text[:80].replace("\n", " ")
        print(
            f"  #{entry.id} [{ts}] user={entry.user_id} agent={entry.agent_id} "
            f"{entry.channel.value} {entry.direction.value}: {preview}"
        )
    if len(logs) == limit:
        print("  (limit reached: narrow the filters or raise the limit for more)")


def _human_size(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{size} bytes" if unit == "bytes" else f"{value:.1f} {unit} ({size} bytes)"
        value /= 1024
    raise AssertionError("unreachable")


def _fmt_time(moment: datetime | None) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC") if moment else "-"


async def _menu_storage() -> None:
    """Storage overview through service.storage_overview (#40), the same
    function GET /storage uses.
    """
    async with session_scope() as session:
        overview = await service.storage_overview(session)
    size = "n/a (not a SQLite file)" if overview.db_size_bytes is None else _human_size(
        overview.db_size_bytes
    )
    print(f"Database size: {size}")
    print("Rows per table:")
    for table, count in overview.row_counts.items():
        print(f"  {table:<20} {count}")
    print(f"Oldest log: {_fmt_time(overview.oldest_log_at)}")
    print(f"Newest log: {_fmt_time(overview.newest_log_at)}")


_MENU = {
    "1": ("Pending access requests", _menu_requests),
    "2": ("Users", _menu_users),
    "3": ("Agents", _menu_agents),
    "4": ("Search logs", _menu_logs),
    "5": ("Storage overview", _menu_storage),
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
