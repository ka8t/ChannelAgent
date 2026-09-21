"""Contract tests for #109: the script's commands are the API's routes, and the script and
the API return the same thing, whether the application is running or stopped.
"""

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.admin import client as cli
from app.admin.manifest import contract_problems, manifest, operations
from app.api.scopes import Scope, _api_routes, require

REPO = Path(__file__).resolve().parent.parent
KEY = "Zq8vT3mK9xW2pL7nR4bY6cH1dF5gJ0sA"


@pytest.fixture
def env(fresh_db, monkeypatch, tmp_path):
    """The environment the script reads (`start.sh` exports it from .env) and a private
    .env for the configuration routes.
    """
    from app.admin.jobs import registry
    from app.api import deps
    from app.config import get_settings

    registry.clear()  # jobs live in the process: no other test's jobs in this one
    old_umask = os.umask(0)
    os.umask(old_umask)  # the client hardens the process umask, as the console does
    example, envfile = tmp_path / ".env.example", tmp_path / ".env"
    shutil.copy(REPO / ".env.example", example)
    shutil.copy(example, envfile)
    envfile.chmod(0o600)
    monkeypatch.setenv("API_SERVER_KEY", KEY)
    monkeypatch.setenv("ENV_FILE", str(envfile))
    monkeypatch.setenv("ENV_EXAMPLE_FILE", str(example))
    get_settings.cache_clear()
    deps.reset_failure_state()
    yield
    os.umask(old_umask)
    registry.clear()
    deps.reset_failure_state()


async def run(*argv: str):
    out, err = io.StringIO(), io.StringIO()
    code = await cli.amain(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()


def _app():
    from app.api.app import app

    return app


# --- the manifest is the routes ---


def test_the_manifest_has_one_command_per_route_and_the_contract_holds():
    routes = [r for r in _api_routes(_app().routes) if isinstance(r, APIRoute)]
    ops = manifest(_app())["operations"]
    print(f"manifest: {len(ops)} commands for {len(routes)} routes")
    assert len(ops) == len(routes) >= 34
    assert len({o["command"] for o in ops}) == len(ops)
    assert contract_problems(_app()) == []


def test_a_route_without_help_text_is_flagged():
    app = FastAPI()

    @app.get("/thing", dependencies=[require(Scope.READ)])
    async def thing():
        return {}

    assert any("no description" in p for p in contract_problems(app))


def test_two_routes_with_one_command_name_are_flagged():
    app = FastAPI()
    for path in ("/a", "/b"):

        async def same():
            """Do it."""

        app.get(path, name="same", dependencies=[require(Scope.READ)])(same)

    assert any("already used" in p for p in contract_problems(app))


def test_every_command_has_a_parser_that_accepts_its_flags():
    parser = cli.build_parser(operations(_app()))
    for op in operations(_app()):
        argv = [op["command"]]
        for f in op["fields"]:
            if f["required"] and f["default"] is None:
                value = (f["enum"] or [None])[0] or ("1" if f["type"] == "integer" else "x")
                argv += [cli._flag(f["name"]), str(value)]
        parser.parse_args(argv)


async def test_describe_lists_every_route_as_a_command(env):
    routes = [r for r in _api_routes(_app().routes) if isinstance(r, APIRoute)]
    code, out, _ = await run("describe", "--json")
    described = json.loads(out)
    assert code == 0 and described["count"] == len(described["operations"]) == len(routes)
    code, text, _ = await run("describe")
    assert text.strip().splitlines()[-1].startswith(f"{len(routes)} commands")


def test_describe_runs_as_a_module_like_start_sh_runs_it():
    result = subprocess.run(
        [sys.executable, "-m", "app.admin.client", "describe", "--json"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "API_SERVER_KEY": ""},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["count"] >= 34


def test_start_sh_offers_the_two_modes():
    script = (REPO / "start.sh").read_text()
    assert '--describe) MODE="describe"' in script and '--api) MODE="api"' in script
    assert "python3 -m app.admin.client" in script


def test_the_engine_is_launched_by_start_sh_without_the_secrets_of_env(tmp_path):
    """The launch prefix is taken from start.sh itself and run with `env` as the child, which
    prints the environment it received: the secrets exported from .env must not be in it.
    """
    import re

    script = (REPO / "start.sh").read_text()
    match = re.search(r'nohup (env -i [^\\]*?)\s*\\\n\s*"\$\{LLAMA_SERVER_BIN\}"', script)
    assert match, "the engine launch line of start.sh changed shape"
    secrets = {
        "ENCRYPTION_KEY": "k1",
        "TELEGRAM_BOT_TOKEN": "k2",
        "EMAIL_PASSWORD": "k3",
        "API_SERVER_KEY": "k4",
        "MATRIX_BOT_ACCESS_TOKEN": "k5",
    }
    exports = "; ".join(f"export {k}={v}" for k, v in secrets.items())

    def child_environment(prefix: str) -> set:
        result = subprocess.run(
            ["bash", "-c", f"{exports}; {prefix} /usr/bin/env"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line}

    assert set(secrets) <= child_environment("nohup"), "the control must show the secrets"
    cleared = child_environment("nohup " + match.group(1))
    print(f"cleared environment keeps: {sorted(cleared)}")
    assert not set(secrets) & cleared


# --- flags, output, errors ---


async def test_flags_are_typed_and_the_output_is_json_or_a_table(env):
    for name in ("Ann", "Bob", "Cy"):
        code, out, _ = await run(
            "create-user", "--display-name", name, "--transport", "inprocess", "--json"
        )
        assert code == 0 and json.loads(out)["display_name"] == name
    code, out, _ = await run(
        "list-users", "--limit", "2", "--offset", "1", "--transport", "inprocess", "--json"
    )
    assert [u["display_name"] for u in json.loads(out)] == ["Bob", "Cy"]
    code, table, _ = await run("list-users", "--transport", "inprocess")
    assert table.splitlines()[0].split() == ["id", "display_name", "is_active"]
    assert "Ann" in table
    code, _, err = await run("list-users", "--limit", "abc", "--transport", "inprocess")
    assert code == 2 and "not a valid integer" in err
    code, _, err = await run("get-user", "--user-id", "999", "--transport", "inprocess", "--json")
    assert code == 1 and "detail" in json.loads(err)


async def test_without_the_key_the_script_says_so_and_calls_nothing(env, monkeypatch):
    monkeypatch.delenv("API_SERVER_KEY")
    code, out, err = await run("list-users", "--transport", "inprocess")
    assert code == 2 and "API_SERVER_KEY is not set" in err and out == ""


async def test_a_script_action_is_recorded_as_cli_and_the_os_user(env):
    await run("create-user", "--display-name", "Dee", "--transport", "inprocess")
    _, out, _ = await run(
        "search-admin-events", "--action", "user.create", "--transport", "inprocess", "--json"
    )
    events = json.loads(out)
    assert len(events) == 1 and events[0]["actor"] == cli.client_label()
    assert events[0]["actor"].startswith("cli:")


# --- the script and the API return the same thing, running or stopped ---


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_application(env):
    """The API in its own process, as the running application is (`uvicorn`, not the test)."""
    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO,
        env={**os.environ, "API_SERVER_KEY": KEY},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            break
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError(proc.stderr.read().decode()) from None
            time.sleep(0.2)
    yield port
    proc.terminate()
    proc.wait(timeout=10)


# Not comparable between two processes by nature: uptime and start time, and an HTML page.
NOT_COMPARABLE = {
    "status": "uptime and start time",
    "docs": "an HTML page",
    "search-admin-events": "reading it is itself audited (#59): the second read sees the first",
    "search-logs": "reading conversation text is audited too, and lists what came before",
}


async def test_every_read_command_returns_the_same_json_stopped_or_running(
    env, running_application, monkeypatch
):
    port = running_application
    monkeypatch.setenv("API_SERVER_PORT", str(port))
    monkeypatch.setenv("API_SERVER_HOST", "127.0.0.1")
    for argv in (
        ["create-user", "--display-name", "Alice"],
        ["add-channel-identity", "--user-id", "1", "--channel", "telegram", "--identifier", "111"],
        ["create-agent", "--user-id", "1", "--name", "helper"],
    ):
        code, _, err = await run(*argv, "--transport", "inprocess")
        assert code == 0, (argv, err)
    known = {"user_id": "1", "channel_identity_id": "1", "agent_id": "1"}
    compared, skipped = [], {}
    for op in operations(_app()):
        if op["method"] != "GET":
            continue
        if op["command"] in NOT_COMPARABLE:
            skipped[op["command"]] = NOT_COMPARABLE[op["command"]]
            continue
        argv = [op["command"]]
        needed = [f for f in op["fields"] if f["required"] and f["default"] is None]
        if any(f["name"] not in known for f in needed):
            skipped[op["command"]] = "needs an id that does not exist here"
            continue
        for f in needed:
            argv += [cli._flag(f["name"]), known[f["name"]]]
        stopped = await run(*argv, "--json", "--transport", "inprocess")
        running = await run(*argv, "--json", "--transport", "http")
        assert stopped[0] == running[0] == 0, (argv, stopped[2], running[2])
        assert json.loads(stopped[1]) == json.loads(running[1]), argv
        compared.append(op["command"])
    print(f"stopped vs running: {len(compared)} compared, 0 differences; skipped {skipped}")
    assert len(compared) >= 12
    wanted = {"list-users", "get-config", "list-database-backups", "openapi-json", "whoami"}
    assert wanted <= set(compared)


# --- jobs, through the script and through HTTP ---


class _ThreadedServer:
    def __init__(self):
        import uvicorn

        self.port = _free_port()
        config = uvicorn.Config(_app(), host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.server.install_signal_handlers = lambda: None
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        while not self.server.started:
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=10)


async def test_a_job_is_started_polled_and_cancelled_through_the_script_and_through_http(
    env, monkeypatch
):
    from app.admin.jobs import registry
    from app.api import operations as ops

    def slow(_path, _label):
        time.sleep(2)

    monkeypatch.setattr(ops, "make_backup", slow)
    registry.clear()
    with _ThreadedServer() as server:
        monkeypatch.setenv("API_SERVER_PORT", str(server.port))
        monkeypatch.setenv("API_SERVER_HOST", "127.0.0.1")
        # through the script
        code, out, _ = await run(
            "create-database-backup", "--no-wait", "--transport", "http", "--json"
        )
        job = json.loads(out)
        assert code == 0 and job["status"] == "running"
        code, out, _ = await run("get-job", "--job-id", job["id"], "--transport", "http", "--json")
        assert code == 0 and json.loads(out)["status"] == "running"
        code, out, _ = await run(
            "cancel-job", "--job-id", job["id"], "--transport", "http", "--json"
        )
        assert code == 0
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            code, out, _ = await run(
                "get-job", "--job-id", job["id"], "--transport", "http", "--json"
            )
            if json.loads(out)["status"] == "cancelled":
                break
            time.sleep(0.1)
        assert json.loads(out)["status"] == "cancelled"
        # through HTTP, the same handlers
        headers = {"Authorization": f"Bearer {KEY}"}
        base = f"http://127.0.0.1:{server.port}"
        started = httpx.post(f"{base}/backups", headers=headers)
        assert started.status_code == 202
        jid = started.json()["id"]
        assert httpx.get(f"{base}/jobs/{jid}", headers=headers).status_code == 200
        assert httpx.post(f"{base}/jobs/{jid}/cancel", headers=headers).status_code == 200
        time.sleep(0.3)
        assert httpx.get(f"{base}/jobs/{jid}", headers=headers).json()["status"] == "cancelled"
    registry.clear()


async def test_an_in_process_job_is_always_waited_for(env):
    code, out, _ = await run(
        "create-database-backup", "--no-wait", "--transport", "inprocess", "--json"
    )
    job = json.loads(out)
    assert code == 0 and job["status"] == "done" and job["result"]["size_bytes"] > 0


async def test_a_job_that_fails_ends_the_command_with_a_failure_and_a_safe_message(
    env, monkeypatch
):
    from app.api import operations as ops
    from app.db.backup import BackupError

    def broken(_path, _label):
        raise BackupError("could not back up test.db: disk full")

    monkeypatch.setattr(ops, "make_backup", broken)
    code, out, err = await run("create-database-backup", "--transport", "inprocess", "--json")
    assert code == 1 and out == ""
    job = json.loads(err)
    assert job["status"] == "failed" and "disk full" in job["error"]
