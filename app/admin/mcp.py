"""MCP server registry service (#116): admin CRUD for app.db.models.McpServer, the
one place this logic lives (mirrors app/admin/service.py's own docstring). Only
administrators declare servers (docs/MCP_EXTENSION.md threat table) — there is no
user-facing way to add one, and `stdio` never runs an admin-supplied command, only
a vetted built-in (app.mcp.builtin.REGISTRY).
"""

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.service import ConflictError, InvalidInputError, NotFoundError, record_admin_event
from app.db.models import McpCall, McpEgress, McpServer, McpTransport
from app.mcp.builtin import REGISTRY as BUILTIN_REGISTRY
from app.mcp.manager import ServerConfig

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}")
MAX_TOOL_NAME_LENGTH = 200
MAX_DISABLED_TOOLS = 200

TRANSPORTS = (McpTransport.STDIO.value, McpTransport.HTTP.value)
EGRESS_LABELS = (McpEgress.LOCAL.value, McpEgress.LAN.value, McpEgress.INTERNET.value)

CONFIG_FIELDS = (
    "url",
    "env_vars",
    "egress",
    "enabled",
    "timeout_seconds",
    "concurrency_limit",
    "result_max_bytes",
    "disabled_tools",
)


class McpServerNotFoundError(NotFoundError):
    pass


class McpServerNameTakenError(ConflictError):
    pass


def _clean_name(value) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise InvalidInputError("A server name is letters, digits, _ and -, up to 100 characters")
    return value


def _clean_env_vars(value) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise InvalidInputError("env_vars is an object of string to string")
    return dict(value)


def _clean_disabled_tools(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_DISABLED_TOOLS:
        raise InvalidInputError(f"disabled_tools is a list of at most {MAX_DISABLED_TOOLS} names")
    for name in value:
        if not isinstance(name, str) or not name or len(name) > MAX_TOOL_NAME_LENGTH:
            raise InvalidInputError("a disabled tool name is non-empty text")
    return list(dict.fromkeys(value))


def _clean_egress(value) -> str:
    if value not in EGRESS_LABELS:
        raise InvalidInputError(f"egress is one of: {', '.join(EGRESS_LABELS)}")
    return value


def _clean_timeout(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 600:
        raise InvalidInputError("timeout_seconds is a whole number from 1 to 600")
    return value


def _clean_concurrency(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        raise InvalidInputError("concurrency_limit is a whole number from 1 to 20")
    return value


def _clean_result_max_bytes(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10_000_000:
        raise InvalidInputError("result_max_bytes is a whole number from 1 to 10,000,000")
    return value


def _clean_enabled(value) -> bool:
    if not isinstance(value, bool):
        raise InvalidInputError("enabled is a boolean")
    return value


def _clean_url(value) -> str:
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise InvalidInputError("url is an http(s) URL")
    return value


_CLEANERS = {
    "url": _clean_url,
    "env_vars": _clean_env_vars,
    "egress": _clean_egress,
    "enabled": _clean_enabled,
    "timeout_seconds": _clean_timeout,
    "concurrency_limit": _clean_concurrency,
    "result_max_bytes": _clean_result_max_bytes,
    "disabled_tools": _clean_disabled_tools,
}


async def _named(session: AsyncSession, name: str) -> McpServer | None:
    return (
        await session.execute(select(McpServer).where(McpServer.name == name))
    ).scalar_one_or_none()


async def get_server(session: AsyncSession, server_id: int) -> McpServer:
    server = await session.get(McpServer, server_id)
    if server is None:
        raise McpServerNotFoundError(f"No MCP server with id {server_id}")
    return server


async def list_servers(session: AsyncSession) -> list[McpServer]:
    return list((await session.execute(select(McpServer).order_by(McpServer.name))).scalars())


async def create_server(
    session: AsyncSession,
    *,
    name: str,
    protocol: str,
    builtin_id: str | None = None,
    fields: dict | None = None,
    actor: str,
) -> McpServer:
    name = _clean_name(name)
    if await _named(session, name) is not None:
        raise McpServerNameTakenError(f"A server named {name!r} already exists")
    if protocol not in TRANSPORTS:
        raise InvalidInputError(f"protocol is one of: {', '.join(TRANSPORTS)}")
    fields = dict(fields or {})
    if protocol == McpTransport.STDIO.value:
        if builtin_id not in BUILTIN_REGISTRY:
            raise InvalidInputError(f"builtin_id is one of: {', '.join(sorted(BUILTIN_REGISTRY))}")
        fields.pop("url", None)
    else:
        if "url" not in fields:
            raise InvalidInputError("an http server needs a url")
        builtin_id = None

    unknown = set(fields) - set(CONFIG_FIELDS)
    if unknown:
        raise InvalidInputError(f"Unknown server settings: {', '.join(sorted(unknown))}")
    cleaned = {key: _CLEANERS[key](value) for key, value in fields.items()}

    server = McpServer(
        name=name,
        protocol=protocol,
        builtin_id=builtin_id,
        url=cleaned.get("url"),
        env_vars=json.dumps(cleaned["env_vars"]) if cleaned.get("env_vars") else None,
        egress=cleaned.get("egress", McpEgress.LOCAL.value),
        enabled=cleaned.get("enabled", True),
        timeout_seconds=cleaned.get("timeout_seconds", 20),
        concurrency_limit=cleaned.get("concurrency_limit", 2),
        result_max_bytes=cleaned.get("result_max_bytes", 1_000_000),
        disabled_tools=cleaned.get("disabled_tools", []),
    )
    session.add(server)
    await session.flush()
    await record_admin_event(
        session,
        actor=actor,
        action="mcp_server.create",
        target_type="mcp_server",
        target_id=server.id,
        details={"name": name, "protocol": protocol, "builtin_id": builtin_id},
    )
    return server


async def configure_server(
    session: AsyncSession, server_id: int, fields: dict, *, actor: str
) -> McpServer:
    server = await get_server(session, server_id)
    unknown = set(fields) - set(CONFIG_FIELDS)
    if unknown:
        raise InvalidInputError(f"Unknown server settings: {', '.join(sorted(unknown))}")
    cleaned = {key: _CLEANERS[key](value) for key, value in fields.items()}
    if "url" in cleaned and server.protocol != McpTransport.HTTP:
        raise InvalidInputError("url only applies to an http server")
    for key, value in cleaned.items():
        if key == "env_vars":
            server.env_vars = json.dumps(value) if value else None
        else:
            setattr(server, key, value)
    await session.flush()
    await record_admin_event(
        session,
        actor=actor,
        action="mcp_server.configure",
        target_type="mcp_server",
        target_id=server.id,
        details={"fields": sorted(cleaned)},
    )
    return server


async def delete_server(session: AsyncSession, server_id: int, *, actor: str) -> None:
    server = await get_server(session, server_id)
    await session.delete(server)
    await session.flush()
    await record_admin_event(
        session,
        actor=actor,
        action="mcp_server.delete",
        target_type="mcp_server",
        target_id=server_id,
        details={"name": server.name},
    )


def to_config(server: McpServer) -> ServerConfig:
    """The manager's own, DB-independent view of one server's settings."""
    return ServerConfig(
        name=server.name,
        protocol=server.protocol,
        builtin_id=server.builtin_id,
        url=server.url,
        env_vars=json.loads(server.env_vars) if server.env_vars else {},
        egress=server.egress,
        timeout_seconds=server.timeout_seconds,
        concurrency_limit=server.concurrency_limit,
        result_max_bytes=server.result_max_bytes,
        disabled_tools=tuple(server.disabled_tools),
    )


async def enabled_configs(session: AsyncSession) -> list[ServerConfig]:
    servers = await list_servers(session)
    return [to_config(s) for s in servers if s.enabled]


async def recent_calls(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> list[McpCall]:
    stmt = select(McpCall).order_by(McpCall.created_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(stmt)).scalars())
