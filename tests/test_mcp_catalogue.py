"""Tests for #116: the tool catalogue — OpenAI-format tool definitions from live
servers filtered by an agent's allow-list, and the executor that dispatches
`mcp__<server>__<tool>` back to the right server and records exactly one McpCall
row per call. Uses the real built-in "time" server over stdio.
"""

import pytest

from app.db.models import McpCall, McpTransport
from app.mcp import catalogue
from app.mcp.manager import Manager, ServerConfig


def _time_config(**overrides) -> ServerConfig:
    base = dict(name="time", protocol=McpTransport.STDIO, builtin_id="time")
    base.update(overrides)
    return ServerConfig(**base)


@pytest.fixture
async def manager():
    m = Manager()
    m.configure([_time_config()])
    yield m
    await m.reset()


@pytest.fixture(autouse=True)
async def _database(fresh_db):
    from app.db.session import init_db

    await init_db()


def test_catalogue_name_round_trips():
    name = catalogue.catalogue_name("time", "get_time")
    assert name == "mcp__time__get_time"
    assert catalogue._split_name(name) == ("time", "get_time")


def test_split_name_rejects_a_non_mcp_name():
    assert catalogue._split_name("get_time") is None
    assert catalogue._split_name("mcp__onlyserver") is None


async def test_build_tools_returns_only_allowed_names(manager):
    tools = await catalogue.build_tools(manager, {"mcp__time__get_time"})
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "mcp__time__get_time"
    assert tools[0]["function"]["parameters"]["required"] == ["timezone"]


async def test_build_tools_excludes_names_not_in_the_allow_list(manager):
    assert await catalogue.build_tools(manager, {"mcp__time__something_else"}) == []


async def test_build_tools_with_nothing_allowed_makes_no_call(manager):
    assert await catalogue.build_tools(manager, set()) == []


async def test_build_tools_skips_a_broken_server_without_crashing():
    m = Manager()
    m.configure([ServerConfig(name="broken", protocol=McpTransport.STDIO, builtin_id="ghost")])
    try:
        assert await catalogue.build_tools(m, {"mcp__broken__x"}) == []
    finally:
        await m.reset()


async def test_build_tools_excludes_a_disabled_tool(manager):
    manager.configure([_time_config(disabled_tools=("get_time",))])
    assert await catalogue.build_tools(manager, {"mcp__time__get_time"}) == []


# --- the executor ---


async def test_the_executor_calls_the_right_server_and_records_one_call(manager):
    from app.db.session import session_scope

    run = catalogue.make_executor(manager, agent_id=7)
    result = await run("mcp__time__get_time", '{"timezone": "UTC"}')
    assert "T" in result  # ISO 8601

    async with session_scope() as session:
        from sqlalchemy import select

        rows = list((await session.execute(select(McpCall))).scalars())
    assert len(rows) == 1
    assert rows[0].agent_id == 7
    assert rows[0].server_name == "time"
    assert rows[0].tool_name == "get_time"
    assert rows[0].status == "ok"
    assert rows[0].duration_ms >= 0


async def test_the_executor_reports_an_unknown_server(manager):
    run = catalogue.make_executor(manager, agent_id=None)
    result = await run("mcp__ghost__x", "{}")
    assert "not available" in result


async def test_the_executor_reports_invalid_json_arguments(manager):
    run = catalogue.make_executor(manager, agent_id=None)
    result = await run("mcp__time__get_time", "not json")
    assert "error" in result


async def test_the_executor_reports_non_object_arguments(manager):
    run = catalogue.make_executor(manager, agent_id=None)
    result = await run("mcp__time__get_time", "[1, 2, 3]")
    assert "error" in result


async def test_the_executor_never_raises_on_a_name_it_cannot_parse(manager):
    run = catalogue.make_executor(manager, agent_id=None)
    result = await run("not-an-mcp-name", "{}")
    assert "unknown tool" in result
