"""Async engine/session setup and startup table creation (#10).

Single place the rest of the app (Auth Node, Admin API) gets a DB
session from, so nothing else constructs its own engine.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_sqlite_dir_exists(database_url: str) -> None:
    """SQLite refuses to create a DB file inside a missing directory —
    ``OperationalError: unable to open database file``, not a clearer
    "no such directory". The Docker image happens to avoid this
    (Dockerfile's mkdir + docker-compose's volume both pre-create
    data/), which is exactly why running natively (start.sh --native)
    was the first thing to actually hit it.
    """
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_engine() -> AsyncEngine:
    database_url = get_settings().database_url
    _ensure_sqlite_dir_exists(database_url)
    return create_async_engine(database_url)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


def _run_migrations_sync(database_url: str) -> None:
    # alembic's Config/command API is synchronous, and env.py's own
    # run_migrations_online() calls asyncio.run() internally — calling
    # it directly from inside app/main.py's already-running event loop
    # would raise "asyncio.run() cannot be called from a running event
    # loop". init_db() below runs this in a separate thread instead.
    from alembic.command import upgrade
    from alembic.config import Config

    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    upgrade(cfg, "head")


async def init_db() -> None:
    """Applies all Alembic migrations up to head (#11). Safe to call on
    every startup — Alembic no-ops if the DB is already current.
    Replaced calling Base.metadata.create_all directly: schema changes
    now go through real migrations (alembic/versions/), tracked by
    revision, instead of requiring the DB to be dropped and recreated.
    """
    database_url = get_settings().database_url
    _ensure_sqlite_dir_exists(database_url)
    await asyncio.to_thread(_run_migrations_sync, database_url)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
