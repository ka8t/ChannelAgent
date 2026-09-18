"""Async engine/session setup and startup table creation (#10).

Single place the rest of the app (Auth Node, Admin API) gets a DB
session from, so nothing else constructs its own engine.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base


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


async def init_db() -> None:
    """Create any missing tables. Safe to call on every startup.

    A stopgap until #11 (Alembic) replaces this with real migrations —
    fine for evolving an empty/dev database, not for altering an
    existing one in place.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
