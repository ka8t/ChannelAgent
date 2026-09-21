"""Who am I and what state is the service in (#133). Both are READ scope."""

import asyncio
import os
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends

from app import health
from app.api.errors import error_responses
from app.api.schemas import DatabaseStatus, EngineStatus, StatusOut, WhoAmIOut
from app.api.scopes import Principal, Scope, get_principal, require
from app.api.version import API_VERSION
from app.config import get_settings
from app.db.backup import _current_revision
from app.db.session import sqlite_file_path

router = APIRouter()

STARTED_AT = datetime.now(UTC)
ENGINE_TIMEOUT_SECONDS = 2.0


@router.get(
    "/whoami",
    dependencies=[require(Scope.READ)],
    response_model=WhoAmIOut,
    tags=["system"],
    responses=error_responses(),
)
async def whoami(principal: Principal = Depends(get_principal)) -> WhoAmIOut:
    """The actor and scope of the caller, and the API version."""
    return WhoAmIOut(
        actor=principal.actor, scope=principal.scope.name.lower(), api_version=API_VERSION
    )


def _database() -> DatabaseStatus:
    url = get_settings().database_url
    path = sqlite_file_path(url)
    if path is None or not path.exists():
        kind = url.split(":", 1)[0].split("+", 1)[0]
        return DatabaseStatus(kind=kind, revision=None, size_bytes=None)
    return DatabaseStatus(
        kind="sqlite", revision=_current_revision(path), size_bytes=path.stat().st_size
    )


async def _engine() -> EngineStatus:
    """Best effort: the engine being down is an answer, not an error."""
    url = get_settings().llama_server_url.rstrip("/") + "/props"
    try:
        async with httpx.AsyncClient(timeout=ENGINE_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
        response.raise_for_status()
        props = response.json()
        model_path = props.get("model_path")
        n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
        return EngineStatus(
            reachable=True,
            model=os.path.basename(model_path) if model_path else None,
            n_ctx=n_ctx if isinstance(n_ctx, int) else None,
        )
    except (httpx.HTTPError, ValueError, AttributeError):
        return EngineStatus(reachable=False)


@router.get(
    "/status",
    dependencies=[require(Scope.READ)],
    response_model=StatusOut,
    tags=["system"],
    responses=error_responses(),
)
async def status() -> StatusOut:
    """Version, uptime, components, database revision and size, engine and its model."""
    now = datetime.now(UTC)
    database, engine = await asyncio.gather(asyncio.to_thread(_database), _engine())
    return StatusOut(
        api_version=API_VERSION,
        started_at=STARTED_AT,
        uptime_seconds=int((now - STARTED_AT).total_seconds()),
        components=health.snapshot(),
        database=database,
        engine=engine,
    )
