"""Tool catalogue (#116): turns the live tools of enabled, connectable servers into
the OpenAI `tools` list app.tools.run_tool_loop needs, and builds the executor that
dispatches `mcp__<server>__<tool>` back to the right server, recording exactly one
app.db.models.McpCall row per call (#116's own minimal audit; #117 broadens it with
confirmation and definition pinning).
"""

import json
import logging
import time

from app.db.models import McpCall
from app.db.session import session_scope
from app.mcp.manager import Manager, McpServerError

logger = logging.getLogger("channelagent")

NAME_PREFIX = "mcp__"


def catalogue_name(server: str, tool: str) -> str:
    return f"{NAME_PREFIX}{server}__{tool}"


def _split_name(name: str) -> tuple[str, str] | None:
    if not name.startswith(NAME_PREFIX):
        return None
    server, sep, tool = name[len(NAME_PREFIX) :].partition("__")
    return (server, tool) if sep else None


async def build_tools(manager: Manager, allowed: set[str]) -> list[dict]:
    """OpenAI-format definitions for every name in `allowed` (an agent's own
    `Agent.tools`, #110) that a live, enabled server actually offers right now. A
    name the agent may use but that no longer exists (server disabled, renamed
    tool) is silently absent, not an error: the model just cannot call it. One
    failing server is skipped, never stops the others' tools from being listed.
    """
    if not allowed:
        return []
    tools: list[dict] = []
    for server in manager.servers():
        try:
            live_tools = await server.list_tools()
        except McpServerError:
            logger.warning(
                "MCP server %r unavailable, its tools are not offered this turn", server.config.name
            )
            continue
        for tool in live_tools:
            if tool.name in server.config.disabled_tools:
                continue
            name = catalogue_name(server.config.name, tool.name)
            if name in allowed:
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema,
                        },
                    }
                )
    return tools


def make_executor(manager: Manager, agent_id: int | None):
    """The `executor(name, raw_arguments)` app.graph.call_llm passes to
    app.tools.run_tool_loop. Never raises (a failure becomes the tool's own error
    text, matching app.tools' contract) and always writes exactly one McpCall row.
    """

    async def run(name: str, raw_arguments: str) -> str:
        parsed = _split_name(name)
        started = time.monotonic()
        status = "error"
        if parsed is None:
            text = f"error: unknown tool {name!r}"
            server_name, tool_name = "", name
        else:
            server_name, tool_name = parsed
            server = manager.get(server_name)
            if server is None:
                text = f"error: server {server_name!r} is not available"
            else:
                try:
                    arguments = json.loads(raw_arguments) if raw_arguments else {}
                    if not isinstance(arguments, dict):
                        raise ValueError("arguments must be a JSON object")
                except (json.JSONDecodeError, ValueError) as exc:
                    text = f"error: invalid arguments: {exc}"
                else:
                    try:
                        text, is_error = await server.call_tool(tool_name, arguments)
                        status = "error" if is_error else "ok"
                    except McpServerError as exc:
                        text = f"error: {exc}"
        duration_ms = int((time.monotonic() - started) * 1000)
        async with session_scope() as session:
            session.add(
                McpCall(
                    agent_id=agent_id,
                    server_name=server_name,
                    tool_name=tool_name,
                    status=status,
                    duration_ms=duration_ms,
                    result_bytes=len(text.encode()),
                )
            )
            await session.commit()
        return text

    return run
