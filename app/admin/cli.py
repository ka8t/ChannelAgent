"""Interactive admin console (#41): ./start.sh --admin.

Every action here calls the same app.admin.service functions the Admin API
routes call (#35's one-service-layer principle): this file is a menu over
existing business logic and holds no query of its own. Every menu is wrapped
so a mistyped answer or a refused operation prints a message and returns to
the menu, it never ends the session.
"""

import asyncio
import enum
import functools
import logging
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta

from app.admin import service
from app.db.models import ActionStatus, Channel, Direction, PermissionKind
from app.db.session import init_db, session_scope
from app.logging_setup import install_redaction
from app.security.permissions import harden_process, warn_about_loose_application_files

logger = logging.getLogger("channelagent")

CONSOLE_ACTOR = "console"
_DEFAULT_LOG_LIMIT = 20


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


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


def _safe(menu: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    """A menu never raises out of the console: bad input and refused
    operations are reported, anything unexpected is logged and reported.
    EOF (input closed) is left to main() to end the session cleanly.
    """

    @functools.wraps(menu)
    async def wrapper() -> None:
        try:
            await menu()
        except _BadInput as exc:
            print(f"Invalid input, nothing changed. {exc}")
        except ValueError as exc:  # every service error is a ValueError
            print(f"Not done: {exc}")
        except (EOFError, KeyboardInterrupt, asyncio.CancelledError):
            raise
        except Exception:
            logger.exception("Console action failed")
            print("Unexpected error, nothing was changed. See the application log.")

    return wrapper


def _int(label: str) -> int:
    """A required whole number."""
    raw = _prompt(label)
    try:
        return int(raw)
    except ValueError as exc:
        raise _BadInput(f"{label}: expected a number, got {raw!r}") from exc


def _required_enum(label: str, enum_cls: type[enum.StrEnum]) -> enum.StrEnum:
    choices = "/".join(e.value for e in enum_cls)
    raw = _prompt(f"{label} ({choices})")
    try:
        return enum_cls(raw.lower())
    except ValueError as exc:
        raise _BadInput(f"{label}: expected one of {choices}, got {raw!r}") from exc


@_safe
async def _menu_requests() -> None:
    async with session_scope() as session:
        pending = await service.list_pending_requests(session)
        if not pending:
            print("No pending requests.")
            return
        for r in pending:
            print(f"  [{r.id}] {r.channel.value}/{r.external_id} -- \"{r.first_message_text}\"")
        if not (raw := _prompt("Request id to resolve (blank to go back)")):
            return
        try:
            request_id = int(raw)
        except ValueError as exc:
            raise _BadInput(f"Request id: expected a number, got {raw!r}") from exc
        action = _prompt("approve/deny")
        if action == "approve":
            user = await service.approve_request(session, request_id, resolved_by=CONSOLE_ACTOR)
            await session.commit()
            print(f"Approved. Created user id={user.id}.")
        elif action == "deny":
            await service.deny_request(session, request_id, resolved_by=CONSOLE_ACTOR)
            await session.commit()
            print("Denied.")
        else:
            print("Unknown action, nothing changed.")


def _print_user_detail(detail: service.UserDetail) -> None:
    u = detail.user
    print(f"  [{u.id}] {u.display_name or '(no name)'} ({'active' if u.is_active else 'inactive'})")
    print("  Channel identities:")
    for i in detail.identities:
        perms = ", ".join(p.value for p in i.permissions) or "no permission"
        talks_to = f" -> agent {i.active_agent_id}" if i.active_agent_id else ""
        print(f"    [{i.id}] {i.channel.value}/{i.external_id}: {perms}{talks_to}")
    if not detail.identities:
        print("    (none)")
    print("  Agents:")
    for a in detail.agents:
        print(f"    [{a.id}] {a.name} ({'active' if a.is_active else 'inactive'})")
    if not detail.agents:
        print("    (none)")


@_safe
async def _menu_users() -> None:
    async with session_scope() as session:
        for u in await service.list_users(session):
            status = "active" if u.is_active else "inactive"
            print(f"  [{u.id}] {u.display_name or '(no name)'} ({status})")
        action = _prompt(
            "detail/create/activate/deactivate/add-identity/remove-identity/"
            "grant/revoke/set-agent/reset-conversation/delete (blank to go back)"
        )
        if not action:
            return
        if action == "detail":
            _print_user_detail(await service.get_user_detail(session, _int("User id")))
        elif action == "create":
            name = _prompt("Display name (blank = none)") or None
            user = await service.create_user(session, name, actor=CONSOLE_ACTOR)
            await session.commit()
            print(f"Created user id={user.id}.")
        elif action in ("activate", "deactivate"):
            active = action == "activate"
            user = await service.update_user(
                session, _int("User id"), is_active=active, actor=CONSOLE_ACTOR
            )
            await session.commit()
            print(f"User {user.id} is now {'active' if user.is_active else 'inactive'}.")
        elif action == "add-identity":
            user_id = _int("User id")
            channel = _required_enum("Channel", Channel)
            identifier = _prompt("Identifier (Telegram id, Matrix id or email address)")
            identity = await service.add_channel_identity(
                session, user_id, channel, identifier, actor=CONSOLE_ACTOR
            )
            await session.commit()
            print(f"Added identity id={identity.id}.")
        elif action == "remove-identity":
            await service.remove_channel_identity(
                session, _int("User id"), _int("Identity id"), actor=CONSOLE_ACTOR
            )
            await session.commit()
            print("Removed.")
        elif action in ("grant", "revoke"):
            user_id, identity_id = _int("User id"), _int("Identity id")
            kind = _required_enum("Permission", PermissionKind)
            if action == "grant":
                await service.grant_identity_permission(
                    session, user_id, identity_id, kind, actor=CONSOLE_ACTOR
                )
            else:
                await service.revoke_identity_permission(
                    session, user_id, identity_id, kind, actor=CONSOLE_ACTOR
                )
            await session.commit()
            print(f"{'Granted' if action == 'grant' else 'Revoked'} {kind.value}.")
        elif action == "set-agent":
            user_id, identity_id = _int("User id"), _int("Identity id")
            raw = _prompt("Agent id it talks to (blank = the default agent)")
            try:
                agent_id = int(raw) if raw else None
            except ValueError as exc:
                raise _BadInput(f"Agent id: expected a number, got {raw!r}") from exc
            await service.set_identity_agent(
                session, user_id, identity_id, agent_id, actor=CONSOLE_ACTOR
            )
            await session.commit()
            print("Now talking to agent " + (str(agent_id) if agent_id else "default") + ".")
        elif action == "reset-conversation":
            user_id = _int("User id")
            raw = _prompt("Agent id (blank = all of this user's agents)")
            try:
                agent_id = int(raw) if raw else None
            except ValueError as exc:
                raise _BadInput(f"Agent id: expected a number, got {raw!r}") from exc
            count = await service.reset_conversation(
                session, user_id, agent_id, actor=CONSOLE_ACTOR
            )
            await session.commit()
            print(f"Reset {count} conversation(s).")
        elif action == "delete":
            user_id = _int("User id")
            purge = _prompt("Type PURGE to also delete agents, logs and conversations (blank = no)")
            report = await service.delete_user(
                session, user_id, purge=purge == "PURGE", actor=CONSOLE_ACTOR
            )
            await session.commit()
            print(
                f"Deleted user {report.user_id} ({report.agents_deleted} agent(s), "
                f"{report.logs_deleted} log entries, {report.threads_deleted} conversation(s))."
            )
        else:
            print("Unknown action, nothing changed.")


@_safe
async def _menu_agents() -> None:
    if not (raw := _prompt("User id (blank to go back)")):
        return
    try:
        user_id = int(raw)
    except ValueError as exc:
        raise _BadInput(f"User id: expected a number, got {raw!r}") from exc
    async with session_scope() as session:
        for a in await service.list_agents(session, user_id):
            print(f"  [{a.id}] {a.name} ({'active' if a.is_active else 'inactive'})")
        action = _prompt("create/rename/activate/deactivate (blank to go back)")
        if action == "create":
            agent = await service.create_agent(
                session, user_id, _prompt("New agent name"), actor=CONSOLE_ACTOR
            )
            await session.commit()
            print(f"Created agent id={agent.id}.")
        elif action == "rename":
            await service.rename_agent(
                session, _int("Agent id"), _prompt("New name"), actor=CONSOLE_ACTOR
            )
            await session.commit()
            print("Renamed.")
        elif action in ("activate", "deactivate"):
            await service.set_agent_active(
                session, _int("Agent id"), action == "activate", actor=CONSOLE_ACTOR
            )
            await session.commit()
            print("Activated." if action == "activate" else "Deactivated.")
        elif action:
            print("Unknown action, nothing changed.")


@_safe
async def _menu_logs() -> None:
    """Search the audit trail through service.search_action_logs (#39),
    the same function GET /logs uses. Blank answers mean "no filter".
    """
    try:
        user_id = _ask_optional("User id (blank = any)", int, "expected a number")
        agent_id = _ask_optional("Agent id (blank = any)", int, "expected a number")
        channel = _ask_enum("Channel", Channel)
        direction = _ask_enum("Direction", Direction)
        status = _ask_enum("Status", ActionStatus)
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
                status=status,
                since=since,
                until=until,
                keyword=keyword,
                limit=limit,
                actor=CONSOLE_ACTOR,
            )
        except ValueError as exc:
            print(f"Invalid input, nothing searched. {exc}")
            return
        await session.commit()  # a read of decrypted logs is itself recorded (#59)
    if not logs:
        print("No matching logs.")
        return
    print(f"{len(logs)} result(s), most recent first:")
    for entry in logs:
        ts = entry.created_at.strftime("%Y-%m-%d %H:%M")
        preview = entry.text[:80].replace("\n", " ")
        flag = "" if entry.status is ActionStatus.OK else f" [{entry.status.value}]"
        print(
            f"  #{entry.id} [{ts}] user={entry.user_id} agent={entry.agent_id} "
            f"{entry.channel.value} {entry.direction.value}{flag}: {preview}"
        )
    if len(logs) == limit:
        print("  (limit reached: narrow the filters or raise the limit for more)")


@_safe
async def _menu_admin_events() -> None:
    """What administrators did, through service.search_admin_events (#59),
    the same function GET /admin-events uses. Blank answers mean "no filter".
    """
    try:
        actor = _prompt("Actor (api/console, blank = any)") or None
        action = _prompt("Action, e.g. user.update (blank = any)") or None
        target_type = _prompt("Target type, e.g. user (blank = any)") or None
        target_id = _ask_optional("Target id (blank = any)", int, "expected a number")
        since = _ask_day("From date")
        until = _ask_day("To date, inclusive", inclusive_end=True)
        asked_limit = _ask_optional("Max results (blank = 20)", int, "expected a number")
        limit = _DEFAULT_LOG_LIMIT if asked_limit is None else asked_limit
    except _BadInput as exc:
        print(f"Invalid input, nothing searched. {exc}")
        return

    async with session_scope() as session:
        try:
            events = await service.search_admin_events(
                session,
                actor=actor,
                action=action,
                target_type=target_type,
                target_id=target_id,
                since=since,
                until=until,
                limit=limit,
                reader=CONSOLE_ACTOR,
            )
        except ValueError as exc:
            print(f"Invalid input, nothing searched. {exc}")
            return
        await session.commit()
    if not events:
        print("No matching events.")
        return
    print(f"{len(events)} result(s), most recent first:")
    for e in events:
        ts = e.created_at.strftime("%Y-%m-%d %H:%M:%S")
        target = f"{e.target_type}#{e.target_id}" if e.target_id is not None else e.target_type
        print(f"  #{e.id} [{ts}] {e.actor} {e.action} {target} {e.details or ''}")
    if len(events) == limit:
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


@_safe
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
    print(f"Undecryptable values: {overview.undecryptable_rows}")
    for table, count in overview.undecryptable_by_table.items():
        print(f"  {table:<20} {count}")


_MENU = {
    "1": ("Pending access requests", _menu_requests),
    "2": ("Users", _menu_users),
    "3": ("Agents", _menu_agents),
    "4": ("Search logs", _menu_logs),
    "5": ("Storage overview", _menu_storage),
    "6": ("Admin events (what administrators did)", _menu_admin_events),
}


async def main() -> None:
    install_redaction()
    harden_process()
    await init_db()
    warn_about_loose_application_files()
    print("=== ChannelAgent Admin Console ===")
    try:
        while True:
            print()
            for key, (label, _) in _MENU.items():
                print(f"{key}. {label}")
            print("q. Quit")
            try:
                choice = _prompt("Choose")
                if choice == "q":
                    break
                entry = _MENU.get(choice)
                if entry is None:
                    print("Unknown option.")
                    continue
                await entry[1]()
            except (EOFError, KeyboardInterrupt):
                print("\nInput closed, leaving the console.")
                break
    finally:
        # A purge opens the conversation checkpoint file, whose connection
        # runs a thread that keeps the process alive until it is closed.
        # Only closed if something imported (and so maybe opened) it.
        graph = sys.modules.get("app.graph")
        if graph is not None:
            await graph.close_graph()


if __name__ == "__main__":
    asyncio.run(main())
