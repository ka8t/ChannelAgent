"""MCP server registry (#116): add, test, enable, per-tool switch. Only an
administrator ever declares a server (docs/MCP_EXTENSION.md threat table); there is
no route a plain user reaches.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin import mcp as service
from app.admin.service import ConflictError
from app.api.actor import current_actor
from app.api.deps import get_db_session
from app.api.errors import error_responses
from app.api.schemas import (
    McpServerIn,
    McpServerOut,
    McpServerTestOut,
    McpServerUpdate,
    McpToolOut,
    McpToolToggleIn,
)
from app.api.scopes import Scope, require
from app.db.models import McpServer
from app.mcp.manager import ManagedServer, McpServerError

router = APIRouter()


def _out(server: McpServer) -> McpServerOut:
    return McpServerOut(
        id=server.id,
        name=server.name,
        protocol=server.protocol,
        builtin_id=server.builtin_id,
        url=server.url,
        has_env_vars=bool(server.env_vars),
        egress=server.egress,
        enabled=server.enabled,
        timeout_seconds=server.timeout_seconds,
        concurrency_limit=server.concurrency_limit,
        result_max_bytes=server.result_max_bytes,
        disabled_tools=list(server.disabled_tools),
        created_at=server.created_at,
    )


async def _connect_one(server: McpServer):
    """One-off connection for /test and GET .../tools, outside the shared manager
    singleton (a test must not leave a live connection other turns then reuse).
    """
    managed = ManagedServer(service.to_config(server))
    try:
        tools = await managed.list_tools()
        return tools, None
    except McpServerError as exc:
        return None, str(exc)
    finally:
        await managed.disconnect()


@router.get(
    "/mcp/servers",
    dependencies=[require(Scope.READ)],
    response_model=list[McpServerOut],
    tags=["mcp"],
    responses=error_responses(),
)
async def list_servers(session: AsyncSession = Depends(get_db_session)) -> list[McpServerOut]:
    """Every declared MCP server, enabled or not."""
    return [_out(s) for s in await service.list_servers(session)]


@router.post(
    "/mcp/servers",
    dependencies=[require(Scope.ADMIN)],
    response_model=McpServerOut,
    status_code=status.HTTP_201_CREATED,
    tags=["mcp"],
    responses=error_responses(409),
)
async def create_server(
    body: McpServerIn, session: AsyncSession = Depends(get_db_session)
) -> McpServerOut:
    """Declare a server: `stdio` names a vetted built-in, `http` an exact URL."""
    server = await service.create_server(
        session,
        name=body.name,
        protocol=body.protocol,
        builtin_id=body.builtin_id,
        fields=body.model_dump(exclude={"name", "protocol", "builtin_id"}, exclude_none=True),
        actor=current_actor(),
    )
    await session.commit()
    return _out(server)


@router.get(
    "/mcp/servers/{server_id}",
    dependencies=[require(Scope.READ)],
    response_model=McpServerOut,
    tags=["mcp"],
    responses=error_responses(404),
)
async def get_server(
    server_id: int, session: AsyncSession = Depends(get_db_session)
) -> McpServerOut:
    """One declared server by id."""
    return _out(await service.get_server(session, server_id))


@router.patch(
    "/mcp/servers/{server_id}",
    dependencies=[require(Scope.ADMIN)],
    response_model=McpServerOut,
    tags=["mcp"],
    responses=error_responses(404, 409),
)
async def update_server(
    server_id: int, body: McpServerUpdate, session: AsyncSession = Depends(get_db_session)
) -> McpServerOut:
    """Change one or more settings of a declared server; a field left out keeps
    its current value."""
    server = await service.configure_server(
        session, server_id, body.model_dump(exclude_none=True), actor=current_actor()
    )
    await session.commit()
    return _out(server)


@router.delete(
    "/mcp/servers/{server_id}",
    dependencies=[require(Scope.ADMIN)],
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["mcp"],
    responses=error_responses(404, 409),
)
async def delete_server(server_id: int, session: AsyncSession = Depends(get_db_session)) -> None:
    """Remove a declared server; already-recorded McpCall rows are unaffected."""
    await service.delete_server(session, server_id, actor=current_actor())
    await session.commit()


@router.post(
    "/mcp/servers/{server_id}/test",
    dependencies=[require(Scope.ADMIN)],
    response_model=McpServerTestOut,
    tags=["mcp"],
    responses=error_responses(404, 409),
)
async def test_server(
    server_id: int, session: AsyncSession = Depends(get_db_session)
) -> McpServerTestOut:
    """Connects once, lists the tools, disconnects — never joins the shared
    manager, so testing a misconfigured server cannot affect a live turn.
    """
    server = await service.get_server(session, server_id)
    tools, error = await _connect_one(server)
    if tools is None:
        return McpServerTestOut(reachable=False, tools=[], error=error)
    return McpServerTestOut(
        reachable=True,
        tools=[
            McpToolOut(name=t.name, description=t.description or "", enabled=True) for t in tools
        ],
    )


@router.get(
    "/mcp/servers/{server_id}/tools",
    dependencies=[require(Scope.READ)],
    response_model=list[McpToolOut],
    tags=["mcp"],
    responses=error_responses(404, 409),
)
async def list_tools(
    server_id: int, session: AsyncSession = Depends(get_db_session)
) -> list[McpToolOut]:
    """A server's tools right now, connecting to it live, each with whether an
    administrator turned it off."""
    server = await service.get_server(session, server_id)
    tools, error = await _connect_one(server)
    if tools is None:
        raise ConflictError(f"{server.name} is not reachable: {error}")
    disabled = set(server.disabled_tools)
    return [
        McpToolOut(name=t.name, description=t.description or "", enabled=t.name not in disabled)
        for t in tools
    ]


@router.patch(
    "/mcp/servers/{server_id}/tools/{tool}",
    dependencies=[require(Scope.ADMIN)],
    response_model=McpServerOut,
    tags=["mcp"],
    responses=error_responses(404, 409),
)
async def toggle_tool(
    server_id: int,
    tool: str,
    body: McpToolToggleIn,
    session: AsyncSession = Depends(get_db_session),
) -> McpServerOut:
    """Enable or disable one of a server's tools without touching the others."""
    server = await service.get_server(session, server_id)
    disabled = set(server.disabled_tools)
    if body.enabled:
        disabled.discard(tool)
    else:
        disabled.add(tool)
    server = await service.configure_server(
        session, server_id, {"disabled_tools": sorted(disabled)}, actor=current_actor()
    )
    await session.commit()
    return _out(server)
