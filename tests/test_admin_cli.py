"""Tests for #41: the interactive admin console. Drives its menu
functions directly with a scripted input() and captures stdout, rather
than spawning start.sh --admin as a real subprocess — same DB/service
layer either way, and this is the part that could actually have a bug.
"""

import pytest


@pytest.mark.asyncio
async def test_approve_request_via_cli_matches_service_layer_result(fresh_db, monkeypatch, capsys):
    from app.admin import cli
    from app.admin.service import request_access
    from app.db.models import Channel
    from app.db.session import init_db, session_scope
    from app.security.auth import authorize

    await init_db()
    async with session_scope() as session:
        req = await request_access(session, Channel.TELEGRAM, "777", "let me in please")
        await session.commit()
        req_id = req.id

    answers = iter([str(req_id), "approve"])
    monkeypatch.setattr("builtins.input", lambda _label="": next(answers))

    await cli._menu_requests()

    async with session_scope() as session:
        decision = await authorize(session, Channel.TELEGRAM, "777")
    assert decision.allowed is True, "CLI approval must match a direct service-layer call"

    out = capsys.readouterr().out
    assert "Approved" in out


@pytest.mark.asyncio
async def test_agents_menu_create_then_deactivate(fresh_db, monkeypatch):
    from app.admin import cli
    from app.db.models import User
    from app.db.session import init_db, session_scope

    await init_db()
    async with session_scope() as session:
        user = User(display_name="CLI test")
        session.add(user)
        await session.flush()
        await session.commit()
        user_id = user.id

    answers = iter([str(user_id), "create", "my-agent"])
    monkeypatch.setattr("builtins.input", lambda _label="": next(answers))
    await cli._menu_agents()

    async with session_scope() as session:
        from app.admin.service import list_agents

        agents = await list_agents(session, user_id)
    assert len(agents) == 1 and agents[0].name == "my-agent"

    answers = iter([str(user_id), "deactivate", str(agents[0].id)])
    monkeypatch.setattr("builtins.input", lambda _label="": next(answers))
    await cli._menu_agents()

    async with session_scope() as session:
        from app.admin.service import list_agents

        agents = await list_agents(session, user_id)
    assert agents[0].is_active is False


@pytest.mark.asyncio
async def test_requests_menu_handles_no_pending_gracefully(fresh_db, capsys):
    from app.admin import cli
    from app.db.session import init_db

    await init_db()
    await cli._menu_requests()
    assert "No pending requests" in capsys.readouterr().out
