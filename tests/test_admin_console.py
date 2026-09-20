"""Tests for the interactive admin console (#41): every action reachable,
no query logic of its own, and no input that can end the session. Also the
API/console parity the issue asks for: the same operation leaves the same
database state through either front end.
"""

import sqlite3

import httpx
import pytest

from app.db.models import Channel, Direction, PermissionKind

KEY = "k" * 32
AUTH = {"Authorization": f"Bearer {KEY}"}


def _script(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda _label="": next(it))


def _db() -> str:
    from app.config import get_settings

    return get_settings().database_url.split("///", 1)[1]


def _sql(query: str, *args):
    con = sqlite3.connect(_db())
    try:
        return con.execute(query, args).fetchall()
    finally:
        con.close()


async def _seed():
    """User 1 Alice: telegram identity 1 (chat), agent default, 1 log entry.
    User 2 Bob: no history. Pending request 1: telegram 777.
    """
    from app.admin import service
    from app.db.session import session_scope

    async with session_scope() as s:
        alice = await service.create_user(s, "Alice")
        await service.create_user(s, "Bob")
        identity = await service.add_channel_identity(s, alice.id, Channel.TELEGRAM, "1")
        await service.grant_identity_permission(s, alice.id, identity.id, PermissionKind.CHAT)
        agent = await service.create_agent(s, alice.id, "default")
        await service.record_action(
            s,
            user_id=alice.id,
            agent_id=agent.id,
            channel=Channel.TELEGRAM,
            direction=Direction.INBOUND,
            text="hello",
        )
        await service.request_access(s, Channel.TELEGRAM, "777", "let me in")
        await s.commit()


@pytest.fixture
async def world(fresh_db):
    from app.db.session import init_db

    await init_db()
    await _seed()


# --- users ---


async def test_user_detail_shows_identities_permissions_and_agents(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "detail", "1")
    await cli._menu_users()
    out = capsys.readouterr().out
    assert "[1] Alice (active)" in out
    assert "[1] telegram/1: chat" in out
    assert "[1] default (active)" in out


async def test_user_detail_of_a_user_with_nothing(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "detail", "2")
    await cli._menu_users()
    out = capsys.readouterr().out
    assert "Bob" in out and out.count("(none)") == 2


async def test_create_activate_and_deactivate_a_user(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "create", "Carol")
    await cli._menu_users()
    assert "Created user id=3." in capsys.readouterr().out
    assert _sql("select display_name, is_active from users where id = 3") == [("Carol", 1)]
    _script(monkeypatch, "deactivate", "3")
    await cli._menu_users()
    assert _sql("select is_active from users where id = 3") == [(0,)]
    _script(monkeypatch, "activate", "3")
    await cli._menu_users()
    assert _sql("select is_active from users where id = 3") == [(1,)]


async def test_add_and_remove_identities_and_grant_and_revoke(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "add-identity", "2", "email", "Bob@Example.com")
    await cli._menu_users()
    assert "Added identity id=2." in capsys.readouterr().out
    ((raw,),) = _sql("select raw_address from channel_identities where id = 2")
    assert raw.startswith("gAAAA"), "the address is encrypted at rest"
    _script(monkeypatch, "grant", "2", "2", "admin")
    await cli._menu_users()
    assert _sql("select kind from permissions where channel_identity_id = 2") == [("admin",)]
    _script(monkeypatch, "revoke", "2", "2", "admin")
    await cli._menu_users()
    assert _sql("select count(*) from permissions where channel_identity_id = 2") == [(0,)]
    _script(monkeypatch, "remove-identity", "2", "2")
    await cli._menu_users()
    assert _sql("select count(*) from channel_identities where id = 2") == [(0,)]


async def test_delete_is_refused_for_a_user_with_history(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "delete", "1", "")
    await cli._menu_users()
    assert "Deactivate the user instead" in capsys.readouterr().out
    assert _sql("select count(*) from users where id = 1") == [(1,)]
    assert _sql("select count(*) from action_logs") == [(1,)]
    _script(monkeypatch, "delete", "1", "purge")  # only the exact word PURGE counts
    await cli._menu_users()
    assert _sql("select count(*) from users where id = 1") == [(1,)]


async def test_delete_without_history_and_purge(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "delete", "2", "")
    await cli._menu_users()
    assert "Deleted user 2" in capsys.readouterr().out
    assert _sql("select count(*) from users where id = 2") == [(0,)]
    _script(monkeypatch, "delete", "1", "PURGE")
    await cli._menu_users()
    out = capsys.readouterr().out
    assert "1 agent(s), 1 log entries" in out
    assert _sql("select count(*) from users") == [(0,)]
    assert _sql("select count(*) from action_logs") == [(0,)]
    assert _sql("select count(*) from agents") == [(0,)]


# --- requests ---


async def test_console_approval_records_the_console_as_actor(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "1", "approve")
    await cli._menu_requests()
    assert "Approved. Created user id=3." in capsys.readouterr().out
    assert _sql("select status, resolved_by from access_requests") == [("approved", "console")]


async def test_console_denial_and_refused_requests(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "1", "deny")
    await cli._menu_requests()
    assert "Denied." in capsys.readouterr().out
    assert _sql("select status, resolved_by from access_requests") == [("denied", "console")]
    assert _sql("select count(*) from users") == [(2,)]
    _script(monkeypatch, "999", "approve")  # nothing pending any more
    await cli._menu_requests()
    assert "No pending requests." in capsys.readouterr().out


async def test_console_unknown_and_already_resolved_request_ids(fresh_db, monkeypatch, capsys):
    from app.admin import cli, service
    from app.db.session import init_db, session_scope

    await init_db()
    async with session_scope() as s:
        await service.request_access(s, Channel.TELEGRAM, "1", "a")
        await s.commit()
    _script(monkeypatch, "999", "approve")
    await cli._menu_requests()
    assert "Not done: No request with id 999" in capsys.readouterr().out


# --- agents ---


async def test_agent_menu_actions(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "1", "create", "work")
    await cli._menu_agents()
    _script(monkeypatch, "1", "rename", "2", "renamed")
    await cli._menu_agents()
    _script(monkeypatch, "1", "deactivate", "2")
    await cli._menu_agents()
    assert _sql("select name, is_active from agents order by id") == [
        ("default", 1),
        ("renamed", 0),
    ]
    _script(monkeypatch, "1", "activate", "2")
    await cli._menu_agents()
    assert _sql("select is_active from agents where id = 2") == [(1,)]
    capsys.readouterr()
    _script(monkeypatch, "1", "rename", "2", "default")
    await cli._menu_agents()
    assert "Not done: User 1 already has an agent named 'default'" in capsys.readouterr().out


async def test_agent_of_an_unknown_user_is_refused(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "999", "create", "ghost")
    await cli._menu_agents()
    assert "Not done: No user with id 999" in capsys.readouterr().out
    assert _sql("select count(*) from agents") == [(1,)]


# --- no input ends the session ---

GARBAGE = ["abc", "-1", "0", "9" * 40, "", "x" * 500, "'; drop table users; --", "🙂", "  ", "1.5"]
MENUS = ["_menu_requests", "_menu_users", "_menu_agents", "_menu_logs", "_menu_storage"]


@pytest.mark.parametrize("garbage", GARBAGE)
@pytest.mark.parametrize("menu", MENUS)
async def test_the_same_garbage_answered_to_every_prompt_never_raises(
    world, monkeypatch, capsys, menu, garbage
):
    from app.admin import cli

    monkeypatch.setattr("builtins.input", lambda _label="": garbage)
    await getattr(cli, menu)()  # must return, whatever it was asked
    assert _sql("select count(*) from users") == [(2,)], "garbage must not change anything"


USER_ACTIONS = [
    "detail",
    "create",
    "activate",
    "deactivate",
    "add-identity",
    "remove-identity",
    "grant",
    "revoke",
    "delete",
]


@pytest.mark.parametrize("garbage", ["abc", "-1", "9" * 40, "", "🙂"])
@pytest.mark.parametrize("action", USER_ACTIONS)
async def test_every_user_action_survives_garbage_arguments(
    world, monkeypatch, capsys, action, garbage
):
    from app.admin import cli

    _script(monkeypatch, action, *([garbage] * 5))
    await cli._menu_users()
    assert capsys.readouterr().out, "something is always printed"
    assert _sql("select count(*) from users where id = 1") == [(1,)], "Alice is never deleted"


@pytest.mark.parametrize("garbage", ["abc", "-1", "9" * 40, "", "🙂"])
@pytest.mark.parametrize("action", ["create", "rename", "activate", "deactivate", "weird"])
async def test_every_agent_action_survives_garbage_arguments(
    world, monkeypatch, capsys, action, garbage
):
    from app.admin import cli

    _script(monkeypatch, "1", action, *([garbage] * 4))
    await cli._menu_agents()
    assert _sql("select count(*) from users") == [(2,)]


async def test_the_main_loop_survives_a_bad_answer_and_unknown_options(world, monkeypatch, capsys):
    from app.admin import cli

    _script(monkeypatch, "2", "detail", "abc", "9", "5", "q")
    await cli.main()
    out = capsys.readouterr().out
    assert "Invalid input, nothing changed." in out
    assert "Unknown option." in out
    assert "Database size:" in out, "the session kept going after the bad answer"


async def test_the_main_loop_ends_cleanly_when_input_is_closed(world, monkeypatch, capsys):
    from app.admin import cli

    def closed(_label=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    await cli.main()
    assert "Input closed" in capsys.readouterr().out


async def test_an_unexpected_error_is_reported_not_raised(world, monkeypatch, capsys):
    from app.admin import cli, service

    async def boom(*a, **k):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(service, "list_users", boom)
    _script(monkeypatch, "")
    await cli._menu_users()
    assert "Unexpected error, nothing was changed" in capsys.readouterr().out


# --- API and console: same service calls, same database state ---

MUTATORS = [
    "approve_request",
    "deny_request",
    "update_user",
    "add_channel_identity",
    "grant_identity_permission",
    "revoke_identity_permission",
    "create_agent",
    "rename_agent",
    "set_agent_active",
    "create_user",
    "remove_channel_identity",
    "delete_user",
]

# name: (api call, console menu, console answers, service functions expected)
OPERATIONS = {
    "approve": (
        lambda c: c.post("/requests/1/approve", headers=AUTH),
        "_menu_requests",
        ["1", "approve"],
        ["approve_request"],
    ),
    "deny": (
        lambda c: c.post("/requests/1/deny", headers=AUTH),
        "_menu_requests",
        ["1", "deny"],
        ["deny_request"],
    ),
    "deactivate-user": (
        lambda c: c.patch("/users/1", json={"is_active": False}, headers=AUTH),
        "_menu_users",
        ["deactivate", "1"],
        ["update_user"],
    ),
    "add-identity": (
        lambda c: c.post(
            "/users/1/channels", json={"channel": "telegram", "identifier": "555"}, headers=AUTH
        ),
        "_menu_users",
        ["add-identity", "1", "telegram", "555"],
        ["add_channel_identity"],
    ),
    "grant": (
        lambda c: c.post("/users/1/channels/1/permissions", json={"kind": "admin"}, headers=AUTH),
        "_menu_users",
        ["grant", "1", "1", "admin"],
        ["grant_identity_permission"],
    ),
    "revoke": (
        lambda c: c.delete("/users/1/channels/1/permissions/chat", headers=AUTH),
        "_menu_users",
        ["revoke", "1", "1", "chat"],
        ["revoke_identity_permission"],
    ),
    "create-agent": (
        lambda c: c.post("/users/1/agents", json={"name": "work"}, headers=AUTH),
        "_menu_agents",
        ["1", "create", "work"],
        ["create_agent"],
    ),
    "rename-agent": (
        lambda c: c.patch("/agents/1", json={"name": "renamed"}, headers=AUTH),
        "_menu_agents",
        ["1", "rename", "1", "renamed"],
        ["rename_agent"],
    ),
    "deactivate-agent": (
        lambda c: c.patch("/agents/1", json={"is_active": False}, headers=AUTH),
        "_menu_agents",
        ["1", "deactivate", "1"],
        ["set_agent_active"],
    ),
    "create-user": (
        lambda c: c.post("/users", json={"display_name": "Carol"}, headers=AUTH),
        "_menu_users",
        ["create", "Carol"],
        ["create_user"],
    ),
    "delete-user-without-history": (
        lambda c: c.delete("/users/2", headers=AUTH),
        "_menu_users",
        ["delete", "2", ""],
        ["delete_user"],
    ),
    "purge-user": (
        lambda c: c.delete("/users/1?purge=true", headers=AUTH),
        "_menu_users",
        ["delete", "1", "PURGE"],
        ["delete_user"],
    ),
    "remove-identity": (
        lambda c: c.delete("/users/1/channels/1", headers=AUTH),
        "_menu_users",
        ["remove-identity", "1", "1"],
        ["remove_channel_identity"],
    ),
}


def _snapshot(path: str) -> dict:
    con = sqlite3.connect(path)
    try:
        q = lambda sql: con.execute(sql).fetchall()  # noqa: E731
        return {
            "users": q("select id, display_name, is_active from users order by id"),
            "identities": q(
                "select id, user_id, channel, external_id from channel_identities order by id"
            ),
            "permissions": q("select id, channel_identity_id, kind from permissions order by id"),
            "agents": q("select id, user_id, name, is_active from agents order by id"),
            "logs": q("select id, user_id, agent_id, status from action_logs order by id"),
            "requests": q(
                "select id, channel, external_id, status, resolved_at is not null "
                "from access_requests order by id"
            ),
        }, q("select id, resolved_by from access_requests order by id")
    finally:
        con.close()


async def _fresh_seeded_db(monkeypatch, path):
    from app.config import get_settings
    from app.db.session import get_engine, get_sessionmaker, init_db

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    await init_db()
    await _seed()


@pytest.mark.parametrize("operation", list(OPERATIONS))
async def test_api_and_console_call_the_same_service_functions_and_leave_the_same_rows(
    fresh_db, monkeypatch, tmp_path, operation
):
    from app.admin import cli, service
    from app.api.app import app
    from app.config import get_settings

    api_call, menu, answers, expected_calls = OPERATIONS[operation]
    monkeypatch.setenv("API_SERVER_KEY", KEY)

    calls: list[str] = []
    for name in MUTATORS:
        real = getattr(service, name)

        def make(real=real, name=name):
            async def wrapper(*a, **k):
                calls.append(name)
                return await real(*a, **k)

            return wrapper

        monkeypatch.setattr(service, name, make())

    # 1. through the API, on database A
    await _fresh_seeded_db(monkeypatch, tmp_path / "api.db")
    del calls[:]  # drop the seeding calls
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        response = await api_call(c)
    assert response.status_code in (200, 201, 204), response.text
    api_calls = list(calls)
    api_state, api_actors = _snapshot(str(tmp_path / "api.db"))

    # 2. through the console, on database B seeded identically
    await _fresh_seeded_db(monkeypatch, tmp_path / "console.db")
    del calls[:]
    _script(monkeypatch, *answers)
    await getattr(cli, menu)()
    console_calls = list(calls)
    console_state, console_actors = _snapshot(str(tmp_path / "console.db"))

    assert api_calls == console_calls == expected_calls
    assert api_state == console_state, "the same operation must leave the same rows"
    get_settings.cache_clear()
    # the only allowed difference: who resolved a request
    if operation in ("approve", "deny"):
        assert api_actors == [(1, "api")] and console_actors == [(1, "console")]
    else:
        assert api_actors == console_actors == [(1, None)]


async def test_the_console_process_exits_after_a_purge(world, monkeypatch):
    """A purge opens the conversation checkpoint file. Its connection runs a
    thread that keeps the process alive until closed, so a console that
    forgot to close it would never return to the shell.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "app.admin.cli"],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo)},
        input="2\ndelete\n1\nPURGE\nq\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "Deleted user 1" in result.stdout and "1 conversation(s)" in result.stdout
    assert _sql("select count(*) from users where id = 1") == [(0,)]
