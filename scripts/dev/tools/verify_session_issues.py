"""Fresh end-to-end checks of the issues implemented on 2026-09-21 (#103, #108, #109, #110,
#133, #104 with #134 to #138), against the current tree, the live container and the live
engine. Nothing is changed in the real data: database work is done on a consistent copy, the
only write to the live application is one backup file (the job of `POST /backups`).

    .venv/bin/python scripts/dev/tools/verify_session_issues.py

Prints one PASS or FAIL line per check with the measured figure; exits 1 if any FAIL.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
PY = str(ROOT / ".venv" / "bin" / "python")
EARLIER = "her" + "mes"  # the name that must not appear anywhere tracked
results: list[tuple[str, str, bool, str]] = []


def check(issue: str, what: str, ok: bool, detail: str = "") -> None:
    results.append((issue, what, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {issue:<9} {what}" + (f"  [{detail}]" if detail else ""))


def dotenv() -> dict:
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value.strip("'\"")
    return values


ENV = dotenv()
KEY = ENV["API_SERVER_KEY"]
BASE = f"http://127.0.0.1:{ENV.get('API_SERVER_PORT', '8700')}"
AUTH = {"Authorization": f"Bearer {KEY}"}
work = Path(tempfile.mkdtemp(prefix="verify-issues-"))
copy = work / "copy.db"
src = sqlite3.connect(f"file:{ROOT / 'data' / 'channelagent.db'}?mode=ro", uri=True)
dst = sqlite3.connect(copy)
src.backup(dst)
src.close(), dst.close()


def client(*args: str, transport: str = "inprocess", db: Path | None = copy):
    """The command-line client, on the copy of the database and the engine on this Mac."""
    env = {**os.environ, **ENV, "LLAMA_SERVER_URL": "http://localhost:8080"}
    if db is not None:
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db}"
    return subprocess.run(
        [PY, "-m", "app.admin.client", *args, "--transport", transport],
        cwd=ROOT, capture_output=True, text=True, env=env, timeout=600,
    )


def sh(*cmd: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def get(path: str, **kw) -> httpx.Response:
    return httpx.get(BASE + path, headers={**AUTH, **kw.pop("headers", {})}, timeout=30, **kw)


# ---------------------------------------------------------------- #103
tracked = sh("git", "grep", "-i", "-c", EARLIER)
check("#103", "no tracked file names the earlier project", tracked.returncode == 1, f"matching files {len(tracked.stdout.split())}")
check("#103", ".env does not name it", EARLIER not in (ROOT / ".env").read_text().lower())
props = httpx.get("http://localhost:8080/props", timeout=10).json()
check("#103", "the engine loads its model from this repository", props["model_path"].startswith("./models/"), props["model_path"])
check("#103", "the model and bundle are not tracked", sh("git", "ls-files", "models", "vendor").stdout.strip() == "")
ctx = sh("sh", "-c", "printf 'FROM scratch\\nCOPY . /ctx\\n' | docker build --no-cache --progress=plain -t verify-ctx -f - . 2>&1 | grep -o 'transferring context: [0-9.]*[A-Za-z]*' | tail -1", timeout=400)
sh("docker", "rmi", "-f", "verify-ctx")
check("#103", "the Docker build context is small", bool(re.search(r"context: [0-9.]+(B|kB|MB)$", ctx.stdout.strip())) and "GB" not in ctx.stdout, ctx.stdout.strip())
img = sh("docker", "inspect", "channelagent-channelagent-1", "--format", "{{.Image}}").stdout.strip()
inside = sh("docker", "run", "--rm", "--entrypoint", "sh", img, "-c", "test -e /app/models -o -e /app/.env -o -e /app/vendor && echo present || echo absent")
check("#103", "the running image holds no model, no .env, no engine bundle", inside.stdout.strip() == "absent")

# ---------------------------------------------------------------- #108
from fastapi.routing import APIRoute  # noqa: E402

from app.api.app import app as api_app  # noqa: E402
from app.api.scopes import _api_routes, declared_scopes, verify_scopes  # noqa: E402

routes = [r for r in _api_routes(api_app.routes) if isinstance(r, APIRoute)]
try:
    verify_scopes(api_app)
    ok = all(len(declared_scopes(r)) == 1 for r in routes)
except RuntimeError:
    ok = False
check("#108", "every route declares exactly one scope", ok, f"{len(routes)} routes")
loose = []
for r in routes:
    body = r.body_field.field_info.annotation if r.body_field is not None else None
    if body is not None and getattr(body, "model_config", {}).get("extra") != "forbid":
        loose.append(r.path)
check("#108", "every request body refuses unknown fields", not loose, f"loose: {loose}")
check("#108", "live: no key -> 401", httpx.get(BASE + "/users", timeout=10).status_code == 401)
check("#108", "live: foreign Host -> 421", get("/users", headers={"Host": "evil.example"}).status_code == 421)
check("#108", "live: foreign Origin on a POST -> 403", httpx.post(BASE + "/users", json={}, headers={**AUTH, "Origin": "https://evil.example"}, timeout=10).status_code == 403)
big = httpx.post(BASE + "/users", content=b"x" * 2_000_000, headers={**AUTH, "Content-Type": "application/json"}, timeout=30)
check("#108", "live: a 2 MB body -> 413", big.status_code == 413, str(big.status_code))
cors = get("/users", headers={"Origin": "https://evil.example"})
check("#108", "live: no CORS header is ever sent", not any(h.lower().startswith("access-control") for h in cors.headers))
check("#108", "live: the API key is in no response body", KEY not in cors.text + big.text)

# ---------------------------------------------------------------- #133
spec = get("/openapi.json").json()
ops = [(m, p, o) for p, item in spec["paths"].items() for m, o in item.items() if m in ("get", "post", "put", "patch", "delete")]
check("#133", "live: every operation has a tag", all(o.get("tags") for *_, o in ops), f"{len(ops)} operations")
check("#133", "live: every operation documents 401, 403 and 429", all({"401", "403", "429"} <= set(o["responses"]) for *_, o in ops))
check("#133", "live: the API version is declared", spec["info"]["version"] == "1", spec["info"]["version"])
users = get("/users", params={"limit": 1})
real = sqlite3.connect(copy).execute("select count(*) from users").fetchone()[0]
check("#133", "live: paging returns 1 and the total is in X-Total-Count", len(users.json()) == 1 and users.headers.get("x-total-count") == str(real), f"total {users.headers.get('x-total-count')} of {real}")
check("#133", "live: limit=0 -> 422", get("/users", params={"limit": 0}).status_code == 422)
st = get("/status").json()
check("#133", "live: /status reports the engine, the model and the revision", st["engine"]["reachable"] and st["engine"]["model"] and st["database"]["revision"] == "b11c1796e218", f"{st['engine']['model']}, ctx {st['engine']['n_ctx']}")
who = get("/whoami").json()
check("#133", "live: /whoami", who == {"actor": "api", "scope": "owner", "api_version": "1"})

# ---------------------------------------------------------------- #109
out = sh("./start.sh", "--describe", "--json", timeout=600).stdout
described = json.loads(out[out.index("{") :])
check("#109", "./start.sh --describe --json lists one command per route", described["count"] == len(routes), f"{described['count']} commands, {len(routes)} routes")
same = 0
for cmd in ("list-users", "list-requests", "list-database-backups"):
    a = client(cmd, "--json", transport="http").stdout
    # the backups sit next to the database file, so that listing is compared on the real path
    # (already at the latest revision, so opening it changes nothing); the others on the copy
    real = ROOT / "data" / "channelagent.db"
    b = client(cmd, "--json", transport="inprocess", db=real if "backups" in cmd else copy).stdout
    same += a.strip() == b.strip() and a.strip() != ""
check("#109", "live application and stopped-mode return the same JSON", same == 3, f"{same} of 3 read commands identical (live vs copy)")
cfg = json.loads(client("get-config", "--json").stdout)
secret_values = [ENV[e["key"]] for e in cfg if e["secret"] and ENV.get(e["key"])]
raw = json.dumps(cfg)
check("#109", "configuration read masks every secret", all(e["value"] is None for e in cfg if e["secret"]) and not any(v in raw for v in secret_values), f"{len(cfg)} variables, {sum(e['secret'] for e in cfg)} secret")
sandbox = work / "cfg"
sandbox.mkdir()
shutil.copy(ROOT / ".env.example", sandbox / ".env.example")
shutil.copy(ROOT / ".env.example", sandbox / ".env")
os.chmod(sandbox / ".env", 0o600)
refused = subprocess.run([PY, "-m", "app.admin.client", "set-config", "--key", "ENCRYPTION_KEY", "--value", "x" * 44, "--transport", "inprocess"], cwd=ROOT, capture_output=True, text=True, env={**os.environ, **ENV, "DATABASE_URL": f"sqlite+aiosqlite:///{copy}", "ENV_FILE": str(sandbox / ".env"), "ENV_EXAMPLE_FILE": str(sandbox / ".env.example")})
check("#109", "ENCRYPTION_KEY cannot be set through the API", refused.returncode == 1 and "cannot be set" in refused.stderr, f"exit {refused.returncode}")
before = sorted(p.name for p in (ROOT / "data" / "backups").iterdir())
job = client("create-database-backup", "--json", transport="http", db=None)
j = json.loads(job.stdout[job.stdout.index("{"):]) if job.stdout else {}
name = (j.get("result") or {}).get("name", "")
made = ROOT / "data" / "backups" / name
integrity = sqlite3.connect(made).execute("pragma integrity_check").fetchone()[0] if made.is_file() else "missing"
check("#109", "live: a backup job runs through the script and the file verifies", j.get("status") == "done" and integrity == "ok" and name not in before, f"{name}, {j.get('result', {}).get('size_bytes')} bytes, integrity {integrity}")
engine = sh("bash", "-c", "grep -c 'env -i PATH' start.sh")
check("#109", "start.sh launches the engine with a cleared environment", engine.stdout.strip() == "1")

# ---------------------------------------------------------------- #135 #136 #137 #138 (#104)
listing = json.loads(client("list-models", "--json").stdout)
check("#135", "list-models shows the installed models with the loaded one marked", len(listing) == 3 and [m for m in listing if m["loaded"]][0]["size_bytes"] == 4920739232, ", ".join(f"{m['name']} {m['size_bytes']}" for m in listing))
recorded = {m["name"]: m["sha256"] for m in listing if m["sha256"]}
hashes = {n: sh("shasum", "-a", "256", str(ROOT / "models" / n)).stdout.split()[0] for n in recorded}
check("#136 #137", "the recorded SHA256 of the imported and the pulled model match the files", bool(recorded) and hashes == recorded, f"{len(recorded)} files re-hashed")
check("#137", "the pulled model has the hub's SHA256", recorded.get("qwen2.5-0.5b-instruct-q4_k_m.gguf") == "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db")
check("#136", "the imported blob has Ollama's digest", recorded.get("qwen2.5-coder-1.5b-instruct-q4_k_m.gguf") == "29d8c98fa6b098e200069bfb88b9508dc3e85586d20cba59f8dda9a808165104")
files_before = sorted(p.name for p in (ROOT / "models").iterdir())
refusals = {
    "http URL": ("pull-model", "--spec", "http://huggingface.co/x/m.gguf"),
    "loopback": ("pull-model", "--spec", "https://127.0.0.1/m.gguf"),
    "metadata address": ("pull-model", "--spec", "https://169.254.169.254/m.gguf"),
    "host off the list": ("pull-model", "--spec", "https://evil.example/m.gguf"),
    "credentials": ("pull-model", "--spec", "https://u:p@huggingface.co/m.gguf"),
    "path in name": ("delete-model", "--name", "../x.gguf"),
    "shell characters": ("delete-model", "--name", "a;b.gguf"),
    "not a gguf": ("import-model", "--path", str(ROOT / ".env"), "--name", "env-copy.gguf"),
    "delete loaded": ("delete-model", "--name", "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"),
}
bad = [k for k, a in refusals.items() if client(*a, "--json").returncode == 0]
check("#134 #135 #136", "nine unsafe requests are all refused", not bad, f"accepted: {bad}")
check("#134 #135 #136", "and nothing was written to models/", sorted(p.name for p in (ROOT / "models").iterdir()) == files_before, f"{len(files_before)} files before and after")
check("#135", "live: the container answers 409 for models (no directory there)", get("/models").status_code == 409)
turn = subprocess.run([PY, "-u", "scripts/dev/no_network_turn.py"], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "LLAMA_SERVER_URL": "http://localhost:8080"}, timeout=200)
check("#138", "a real chat turn: HTTP 200 and 0 connections outside the machine", turn.returncode == 0 and "[200]" in turn.stdout and "outside this machine: 0" in turn.stdout, turn.stdout.strip().splitlines()[-2:][0] if turn.stdout else turn.stderr[-80:])

# ---------------------------------------------------------------- #110
real_db = sqlite3.connect(f"file:{ROOT / 'data' / 'channelagent.db'}?mode=ro", uri=True)
cols = [c[1] for c in real_db.execute("pragma table_info(agents)")]
check("#110", "the real database has the four columns and its revision", {"system_prompt", "model", "memory_mode", "tools"} <= set(cols) and real_db.execute("select version_num from alembic_version").fetchone()[0] == "b11c1796e218", f"{real_db.execute('select count(*) from agents').fetchone()[0]} agents")
alembic = subprocess.run([PY, "-m", "alembic", "check"], cwd=ROOT, capture_output=True, text=True, env={**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{ROOT / 'data' / 'channelagent.db'}"})
check("#110", "alembic check on the real database", alembic.returncode == 0, alembic.stdout.strip().splitlines()[-1] if alembic.stdout.strip() else alembic.stderr[-60:])
agent = get("/agents/1").json()
check("#110", "live: an agent carries the four settings", {"system_prompt", "has_system_prompt", "model", "memory_mode", "tools"} <= set(agent), str({k: agent[k] for k in ("model", "memory_mode", "tools")}))
PROMPT = "You are a verification agent, private instructions 4f9c2a."
created = client("create-agent", "--user-id", "1", "--name", "verify-agent", "--system-prompt", PROMPT, "--memory-mode", "search", "--tools", '["t1","t2"]', "--json")
c = json.loads(created.stdout[created.stdout.index("{"):]) if created.returncode == 0 else {}
raw_col = sqlite3.connect(copy).execute("select system_prompt from agents where name = 'verify-agent'").fetchone()
check("#110", "a prompt set through the script is encrypted in the column and read back as an administrator", bool(c) and c.get("system_prompt") == PROMPT and raw_col and PROMPT not in raw_col[0] and "4f9c2a" not in raw_col[0], f"stored {len(raw_col[0]) if raw_col else 0} characters, 0 in clear")
bad_mode = client("update-agent", "--agent-id", str(c.get("id", 1)), "--memory-mode", "sometimes", "--json")
check("#110", "an invalid memory mode is refused by the script", bad_mode.returncode != 0)

shutil.rmtree(work, ignore_errors=True)
failed = [r for r in results if not r[2]]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed of {len(results)} checks")
sys.exit(1 if failed else 0)
