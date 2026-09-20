"""Tests for #52: the Admin API must not be reachable from the network by
default. It serves decrypted conversations behind one static key over
plain HTTP.
"""

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_api_binds_to_loopback_by_default(monkeypatch):
    monkeypatch.delenv("API_SERVER_HOST", raising=False)
    from app.config import Settings

    assert Settings(_env_file=None).api_server_host == "127.0.0.1"


def test_api_host_can_be_widened_explicitly(monkeypatch):
    monkeypatch.setenv("API_SERVER_HOST", "0.0.0.0")
    from app.config import Settings

    assert Settings(_env_file=None).api_server_host == "0.0.0.0"


def test_compose_publishes_the_api_on_loopback_by_default():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
    ports = compose["services"]["channelagent"]["ports"]
    assert ports == [
        "${API_BIND_ADDRESS:-127.0.0.1}:${API_SERVER_PORT:-8700}:${API_SERVER_PORT:-8700}"
    ]


def test_compose_makes_the_api_listen_on_every_interface_inside_the_container():
    compose = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text())
    env = compose["services"]["channelagent"]["environment"]
    assert env["API_SERVER_HOST"] == "0.0.0.0"
    assert "ENV API_SERVER_HOST=0.0.0.0" in (REPO_ROOT / "Dockerfile").read_text()


def test_env_example_documents_both_addresses_with_loopback_defaults():
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    assert "API_SERVER_HOST=127.0.0.1" in lines
    assert "API_BIND_ADDRESS=127.0.0.1" in lines


@pytest.mark.parametrize(
    ("key", "acceptable"),
    [(None, False), ("", False), ("short", False), ("x" * 15, False),
     ("x" * 16, True), ("a" * 64, True)],
)
def test_short_or_missing_api_key_is_not_acceptable(key, acceptable):
    from app.api.deps import api_key_is_acceptable

    assert api_key_is_acceptable(key) is acceptable


async def test_main_does_not_start_the_api_with_a_short_key(fresh_db, monkeypatch, caplog):
    import asyncio
    import logging

    from app import main as app_main
    from app.config import get_settings

    monkeypatch.setenv("API_SERVER_KEY", "short")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("EMAIL_IMAP_HOST", "")
    get_settings.cache_clear()

    started = []
    monkeypatch.setattr("uvicorn.Server.serve", lambda self: started.append(self))

    caplog.set_level(logging.INFO, logger="channelagent")
    task = asyncio.create_task(app_main.main())
    await asyncio.sleep(0)
    for _ in range(50):
        if any("Admin API NOT started" in r.message for r in caplog.records):
            break
        await asyncio.sleep(0.05)
    task.cancel()
    assert any("Admin API NOT started" in r.message for r in caplog.records)
    assert started == [], "uvicorn must not be started with a weak key"


@pytest.mark.parametrize(("env_host", "expected"), [(None, "127.0.0.1"), ("0.0.0.0", "0.0.0.0")])
async def test_main_starts_uvicorn_on_the_configured_host(
    fresh_db, monkeypatch, env_host, expected
):
    import asyncio

    import uvicorn

    from app import main as app_main
    from app.config import get_settings

    monkeypatch.setenv("API_SERVER_KEY", "k" * 32)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("EMAIL_IMAP_HOST", "")
    if env_host is None:
        monkeypatch.delenv("API_SERVER_HOST", raising=False)
    else:
        monkeypatch.setenv("API_SERVER_HOST", env_host)
    get_settings.cache_clear()

    seen: dict = {}

    class SpyConfig:
        def __init__(self, app, **kwargs):
            seen.update(kwargs)

    class SpyServer:
        def __init__(self, config):
            pass

        async def serve(self):
            await asyncio.sleep(3600)

    monkeypatch.setattr(uvicorn, "Config", SpyConfig)
    monkeypatch.setattr(uvicorn, "Server", SpyServer)

    task = asyncio.create_task(app_main.main())
    for _ in range(100):
        if seen:
            break
        await asyncio.sleep(0.05)
    task.cancel()
    assert seen["host"] == expected
