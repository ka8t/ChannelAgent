"""Shared pytest fixtures.

ENCRYPTION_KEY must be set before app.config is imported anywhere
(get_settings() is required, no default) — set at collection time,
before any test module imports app.* code.
"""

import os

os.environ.setdefault("ENCRYPTION_KEY", "x363KqoSjUm_XlMo1PsoINijTKX6-1OKBMbQN84ZJGY=")

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
