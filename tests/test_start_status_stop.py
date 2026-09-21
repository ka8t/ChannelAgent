"""Tests for #77: ./start.sh --status and --stop.

Every run is in a temporary directory holding a copy of start.sh. Components
are real processes: a stub `llama-server` (a script of that name serving
/health), a stub Admin API, a fake `app.main`, and a fake `docker` that only
records what it was asked. Nothing touches the real application, the real
llama-server or Docker.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parent.parent

LLAMA_STUB = textwrap.dedent(
    """
    import sys
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass
        def do_GET(self):
            code = 200 if self.path == "/health" else 404
            self.send_response(code); self.send_header("Content-Length", "2"); self.end_headers()
            self.wfile.write(b"ok")

    HTTPServer(("127.0.0.1", int(sys.argv[sys.argv.index("--port") + 1])), H).serve_forever()
    """
)

FAKE_DOCKER = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_DOCKER_LOG"
if [ "$1 $2 $3" = "compose ps --status" ]; then
  [ -f "$FAKE_DOCKER_STATE" ] && echo "0123456789abcdef"
  exit 0
fi
if [ "$1 $2 $3" = "compose stop channelagent" ]; then
  rm -f "$FAKE_DOCKER_STATE"
  exit 0
fi
exit 0
"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait(condition, timeout=15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


class Box:
    """A sandbox directory plus the helpers to start stub components in it."""

    def __init__(self, path: Path):
        self.path = path
        self.procs: list[subprocess.Popen] = []
        self.llama_port = _free_port()
        self.api_port = _free_port()
        shutil.copy(REPO / "start.sh", path / "start.sh")
        shutil.copy(REPO / ".env.example", path / ".env.example")
        (path / "app").mkdir()
        shutil.copy(REPO / "app" / "settings_rules.py", path / "app" / "settings_rules.py")
        (path / "bin").mkdir()
        (path / "bin" / "docker").write_text(FAKE_DOCKER)
        (path / "bin" / "docker").chmod(0o755)
        (path / "bin" / "llama-server").write_text(LLAMA_STUB)
        self.docker_log = path / "docker.log"
        self.docker_state = path / "docker.running"
        self.write_env(api_key="k" * 32)

    def write_env(self, api_key: str = ""):
        (self.path / ".env").write_text(
            f"LLAMA_PORT={self.llama_port}\nAPI_SERVER_PORT={self.api_port}\n"
            f"API_SERVER_KEY={api_key}\nENCRYPTION_KEY=x\n"
        )
        (self.path / ".env").chmod(0o600)

    def start_llama(self, pidfile=True) -> subprocess.Popen:
        script = str(self.path / "bin" / "llama-server")
        proc = subprocess.Popen([sys.executable, script, "--port", str(self.llama_port)])
        self.procs.append(proc)
        assert _wait(lambda: httpx_ok(f"http://127.0.0.1:{self.llama_port}/health"))
        if pidfile:
            (self.path / ".llama-server.pid").write_text(str(proc.pid))
        return proc

    def start_foreign_llama_lookalike(self) -> subprocess.Popen:
        """Serves /health on the llama port, but its command line does not say
        llama-server: a process this script did not start.
        """
        code = LLAMA_STUB
        proc = subprocess.Popen(
            [sys.executable, "-c", code, "--port", str(self.llama_port)],
        )
        self.procs.append(proc)
        assert _wait(lambda: httpx_ok(f"http://127.0.0.1:{self.llama_port}/health"))
        return proc

    def start_native_app(self) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)", "app.main"])
        self.procs.append(proc)
        (self.path / ".app.pid").write_text(str(proc.pid))
        return proc

    def start_unrelated(self) -> subprocess.Popen:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.procs.append(proc)
        return proc

    def run(self, *args: str, docker=True, extra_env=None):
        path = f"{self.path / 'bin'}:/usr/bin:/bin" if docker else "/usr/bin:/bin"
        env = {
            "PATH": path,
            "HOME": str(self.path),
            "FAKE_DOCKER_LOG": str(self.docker_log),
            "FAKE_DOCKER_STATE": str(self.docker_state),
            **(extra_env or {}),
        }
        return subprocess.run(
            ["bash", "start.sh", *args],
            cwd=self.path,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )

    def docker_calls(self) -> list[str]:
        return self.docker_log.read_text().splitlines() if self.docker_log.exists() else []

    def cleanup(self):
        for proc in self.procs:
            if proc.poll() is None:
                proc.send_signal(signal.SIGKILL)
                proc.wait(timeout=10)


def httpx_ok(url: str) -> bool:
    try:
        return httpx.get(url, timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def box(tmp_path):
    b = Box(tmp_path)
    yield b
    b.cleanup()


@pytest.fixture
def api_stub(box):
    """An Admin API stand-in that answers 401 without a key, like the real one."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = HTTPServer(("127.0.0.1", box.api_port), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


def _line(output: str, label: str) -> str:
    return next(line for line in output.splitlines() if line.strip().startswith(label))


# --- --status ---


def test_status_reports_everything_down(box):
    result = box.run("--status")
    assert result.returncode == 0, result.stderr
    assert "app (container)  : not running" in result.stdout
    assert "app (native)     : not running" in result.stdout
    assert f"Admin API        : down on 127.0.0.1:{box.api_port}" in result.stdout
    assert f"llama-server     : down on port {box.llama_port}" in result.stdout


def test_status_reports_each_component_up(box, api_stub):
    llama = box.start_llama()
    native = box.start_native_app()
    box.docker_state.write_text("running")

    out = box.run("--status").stdout

    assert "app (container)  : running (0123456789ab)" in out
    assert f"app (native)     : running (pid {native.pid})" in out
    assert f"up on 127.0.0.1:{box.api_port} (HTTP 401)" in _line(out, "Admin API")
    assert f"up on port {box.llama_port} (pid {llama.pid}, started by start.sh)" in out


def test_status_says_when_the_llama_server_was_not_started_by_the_script(box):
    box.start_foreign_llama_lookalike()
    out = box.run("--status").stdout
    assert "(not started by start.sh)" in _line(out, "llama-server")


def test_a_pid_file_naming_an_unrelated_process_does_not_count_as_the_app(box):
    other = box.start_unrelated()
    (box.path / ".app.pid").write_text(str(other.pid))
    assert "app (native)     : not running" in box.run("--status").stdout


def test_status_without_docker_says_so(box):
    out = box.run("--status", docker=False).stdout
    assert "docker not available" in _line(out, "app (container)")


def test_status_says_the_api_is_disabled_without_a_key(box):
    box.write_env(api_key="")
    assert "disabled (API_SERVER_KEY is not set)" in box.run("--status").stdout


def test_status_reads_and_changes_nothing(box):
    before = (box.path / ".env").read_bytes()
    box.run("--status")
    assert (box.path / ".env").read_bytes() == before
    assert not (box.path / ".env.bak").exists()
    assert box.docker_calls() == ["compose ps --status running -q channelagent"]


# --- --stop ---


def test_stop_stops_the_native_app_and_the_container_but_not_the_llama_server(box):
    llama = box.start_llama()
    native = box.start_native_app()
    box.docker_state.write_text("running")

    result = box.run("--stop")

    assert result.returncode == 0, result.stderr
    assert _wait(lambda: native.poll() is not None), "the native app is stopped"
    assert not (box.path / ".app.pid").exists()
    assert "compose stop channelagent" in box.docker_calls()
    assert not box.docker_state.exists()
    assert llama.poll() is None, "llama-server keeps running without --all"
    assert "left as it is" in result.stdout


def test_stop_all_also_stops_the_llama_server_it_started(box):
    llama = box.start_llama()
    result = box.run("--stop", "--all")
    assert result.returncode == 0, result.stderr
    assert _wait(lambda: llama.poll() is not None)
    assert not (box.path / ".llama-server.pid").exists()
    assert not httpx_ok(f"http://127.0.0.1:{box.llama_port}/health")


def test_stop_never_signals_a_process_that_is_not_ours(box):
    """The pid file names a foreign server that answers on the llama port: it
    must be left running, and the file kept.
    """
    foreign = box.start_foreign_llama_lookalike()
    (box.path / ".llama-server.pid").write_text(str(foreign.pid))

    result = box.run("--stop", "--all")

    assert foreign.poll() is None, "the foreign process is untouched"
    assert httpx_ok(f"http://127.0.0.1:{box.llama_port}/health")
    assert (box.path / ".llama-server.pid").read_text() == str(foreign.pid)
    assert "left alone" in result.stderr


def test_stop_never_signals_an_unrelated_process_named_by_the_app_pid_file(box):
    other = box.start_unrelated()
    (box.path / ".app.pid").write_text(str(other.pid))
    box.run("--stop")
    assert other.poll() is None
    assert (box.path / ".app.pid").exists()


def test_a_stale_pid_file_is_removed_and_nothing_is_killed(box):
    gone = box.start_unrelated()
    gone.kill()
    gone.wait()
    (box.path / ".app.pid").write_text(str(gone.pid))
    result = box.run("--stop")
    assert result.returncode == 0
    assert not (box.path / ".app.pid").exists()
    assert "stale" in result.stdout


def test_stop_only_asks_docker_to_stop_the_channelagent_service(box):
    box.docker_state.write_text("running")
    box.run("--stop", "--all")
    calls = box.docker_calls()
    assert "compose stop channelagent" in calls
    assert not [c for c in calls if c.split()[0] in ("kill", "rm", "stop", "system")]
    assert not [c for c in calls if " down" in c or " rm" in c or " kill" in c]


def test_stop_with_nothing_running_is_fine(box):
    result = box.run("--stop", "--all")
    assert result.returncode == 0
    assert "compose stop" not in " ".join(box.docker_calls())


def test_stop_rejects_an_unknown_argument(box):
    llama = box.start_llama()
    result = box.run("--stop", "--everything")
    assert result.returncode == 1 and "Usage" in result.stderr
    assert llama.poll() is None


# --- the notice after --set ---


def test_set_says_the_change_applies_at_the_next_start_and_restarts_nothing(box):
    box.docker_state.write_text("running")
    result = box.run("--set", "LLAMA_CTX_SIZE=32768")
    assert result.returncode == 0, result.stderr
    assert "Applies at the next start" in result.stdout
    assert box.docker_calls() == [], "--set never touches Docker"
    assert box.docker_state.exists(), "and the container keeps running"


# --- the native start leaves the pid that --status and --stop look for ---


def test_the_native_start_records_its_pid_just_before_exec():
    """`exec` keeps the pid, so what is written is the application's own pid.
    Running --native needs a venv and a model server, so this reads the script.
    """
    lines = [line.strip() for line in (REPO / "start.sh").read_text().splitlines()]
    exec_at = lines.index("exec python3 -m app.main")
    assert lines[exec_at - 1] == "echo $$ > .app.pid"
