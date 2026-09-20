"""Shared pytest fixtures.

The ENCRYPTION_KEY below is a throwaway key used by the tests only. It has never
protected real data: the real key lives in .env and must never appear in a
tracked file (tests/test_no_committed_secrets.py fails if a Fernet-shaped key
appears anywhere else).

ENCRYPTION_KEY must be set before app.config is imported anywhere
(get_settings() is required, no default) — set at collection time,
before any test module imports app.* code.
"""

import os

os.environ.setdefault("ENCRYPTION_KEY", "PmKTledxEc-gdO4tty5QO4PjB48zp_GqWMVIpigdwEg=")

import pytest


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Points DATABASE_URL at a fresh, empty SQLite file for one test,
    and clears the lru_cache'd Settings/engine/sessionmaker so the new
    value actually takes effect instead of reusing a previous test's.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    from app.config import get_settings
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    yield

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(autouse=True)
async def isolated_checkpoints(tmp_path, monkeypatch):
    """Every test gets its own checkpoint file (#49), so no test can write
    into the real data/ directory, and the checkpoint connection, which
    belongs to the test's event loop, is closed when the test ends.
    """
    monkeypatch.setenv("CHECKPOINT_DB_PATH", str(tmp_path / "checkpoints.db"))
    from app.config import get_settings
    from app.db import types

    get_settings.cache_clear()
    types.reset_warning_state()
    yield
    from app import graph

    await graph.close_graph()
