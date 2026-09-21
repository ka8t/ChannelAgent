#!/usr/bin/env bash
# Guided entry point for local development.
#
# Two run modes, because LLAMA_SERVER_URL must differ between them (see
# docs/ARCHITECTURE.md, "Compute topology" — host.docker.internal only
# resolves inside a container):
#   ./start.sh            -> docker compose up --build (default; matches
#                             the project's actual deployment target)
#   ./start.sh --native   -> run app/main.py directly via a local venv,
#                             for fast iteration without a rebuild each time
#
# Plus two config-management commands (#34), so every variable the app
# needs can be read/changed without opening .env in an editor:
#   ./start.sh --show-config       -> list every variable from
#                                      .env.example with its current
#                                      .env value (secrets masked)
#   ./start.sh --set KEY=VALUE     -> add or update one variable in .env
#
# Plus the interactive admin console (#41) — users, access requests,
# agents, action logs — over the local venv, no llama-server needed:
#   ./start.sh --admin
#
# And the guided restore of a database backup (#76), with the application
# stopped: lists the backups, checks the chosen one, keeps the current database
# as a "before-restore" copy, then swaps it in:
#   ./start.sh --restore [FILE] [--list] [--yes] [--allow-unreadable]
#
# And what runs, and how to stop it (#77):
#   ./start.sh --status          -> app (container or native), Admin API,
#                                    llama-server: up or down
#   ./start.sh --stop [--all]    -> stop the native app or the container;
#                                    with --all also the llama-server this
#                                    script started. Only processes it can
#                                    identify as its own are ever signalled.
#
# And the guided rotation of the encryption key (#78), application stopped:
# dry run, confirmation, re-encryption with backups, read-back, what to delete:
#   ./start.sh --rekey [--dry-run] [--yes] [--allow-unreadable]
#
# Both run modes need a native llama-server running on this Mac first
# (Metal-accelerated inference). If it isn't already reachable on
# LLAMA_PORT, this script starts it itself, using LLAMA_SERVER_BIN /
# MODELS_DIR / MODEL_FILE from .env (same invocation as Hermes's own
# macos-arm64/scripts/run-llama-server.sh) — then leaves it running in
# the background rather than stopping it on exit: reloading the model
# costs real time at this context size, so killing it every run would
# make iteration painfully slow (same reasoning Hermes documents for
# never idle-unloading it).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

# .env holds every secret: it is created readable by its owner only (#68),
# whatever the caller's umask. A .env that already exists is never changed,
# only reported when other users can read it.
create_env_from_example() {
  (umask 077; cp .env.example .env)
}

warn_if_env_is_shared() {
  local mode
  mode="$(python3 -c "import os; print(format(os.stat('.env').st_mode & 0o777, 'o'))")"
  if [ $(( 8#$mode & 8#077 )) -ne 0 ]; then
    echo "!! .env is readable by other users (mode ${mode}) and holds secrets. Restrict it: chmod 600 .env" >&2
  fi
}

show_config() {
  if [ ! -f .env ]; then
    echo "No .env found — copying from .env.example." >&2
    create_env_from_example
  fi
  warn_if_env_is_shared
  python3 - <<'PYEOF'
SENSITIVE = {
    "ENCRYPTION_KEY",
    "API_SERVER_KEY",
    "TELEGRAM_BOT_TOKEN",
    "EMAIL_PASSWORD",
    "MATRIX_ACCESS_TOKEN",
    "MATRIX_BOT_ACCESS_TOKEN",
}


def load(path):
    values = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                # --set writes a value with special characters in single quotes (#80)
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                values[key] = value
    except FileNotFoundError:
        pass
    return values


example = load(".env.example")
current = load(".env")

print("Current configuration (keys from .env.example, values from .env):\n")
for key in example:
    value = current.get(key, "")
    if key in SENSITIVE:
        display = f"{value[:4]}...(hidden)" if value else "(not set)"
    else:
        display = value if value else "(not set)"
    print(f"  {key:<28} {display}")
PYEOF
}

set_config() {
  local kv="${1:-}"
  if [[ "$kv" != *=* ]]; then
    echo "Usage: ./start.sh --set KEY=VALUE" >&2
    exit 1
  fi
  local key="${kv%%=*}"
  local value="${kv#*=}"
  if ! [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
    echo "'${key}' is not a valid variable name (UPPER_CASE letters, digits and underscores)." >&2
    exit 1
  fi
  if [ ! -f .env ]; then
    create_env_from_example
  fi
  warn_if_env_is_shared
  python3 - "$key" "$value" <<'PYEOF'
import difflib
import os
import sys

key, value = sys.argv[1], sys.argv[2]
path = ".env"

# Only variables the application knows (the ones in .env.example): a typo
# such as LLAMA_PROT would otherwise be written silently and ignored.
known = []
with open(".env.example") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            known.append(line.partition("=")[0])
if key not in known:
    close = difflib.get_close_matches(key, known, n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    print(f"unknown variable '{key}'.{hint} Known variables: {', '.join(known)}", file=sys.stderr)
    sys.exit(1)

with open(path) as f:
    lines = f.readlines()

# ENCRYPTION_KEY reads every encrypted value (messages, admin events, email
# addresses, conversation checkpoints). Overwriting it makes all of them
# unreadable, so a key already in place is never replaced here: only the
# rotation tool re-encrypts the data under a new key (#74). It is never echoed.
if key == "ENCRYPTION_KEY":
    current = next((ln.split("=", 1)[1].strip() for ln in lines if ln.startswith("ENCRYPTION_KEY=")), "")
    if current.strip("'\"") != "":  # ENCRYPTION_KEY='' is empty
        print(
            "ENCRYPTION_KEY is already set and was NOT changed: replacing it would make every "
            "encrypted value unreadable. Rotate it with ./start.sh --rekey, which re-encrypts the "
            "data (or python -m app.admin.rekey by hand, see docs/ARCHITECTURE.md, "
            "'Encryption key: backup, loss and rotation').",
            file=sys.stderr,
        )
        sys.exit(1)

# The value rules (ports, hosts, URLs, key strength, the Fernet format...) and how a
# value is written to .env are app/settings_rules.py, the same module the
# application imports for the API key rule (#75, #80). Nothing is written when it
# says no, or when it cannot be loaded.
sys.path.insert(0, os.path.join(os.getcwd(), "app"))
try:
    import settings_rules
except ImportError as exc:
    print(f"{key} was NOT changed: the value rules could not be loaded ({exc}).", file=sys.stderr)
    sys.exit(1)
reason = settings_rules.validate(key, value)
if reason:
    print(f"{key} was NOT changed: the value {reason}", file=sys.stderr)
    sys.exit(1)
written = settings_rules.format_value(value)

# Every change keeps the previous .env as .env.bak (one generation, mode 600, git-ignored)
# so a bad edit can be undone. Written only once the change is accepted.
with open(path, "rb") as f:
    previous = f.read()
fd = os.open(path + ".bak", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
try:
    os.fchmod(fd, 0o600)
    os.write(fd, previous)
finally:
    os.close(fd)
print("Previous .env saved as .env.bak (mode 600).")

found = False
for i, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[i] = f"{key}={written}\n"
        found = True
        break
if not found:
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.append(f"{key}={written}\n")

with open(path, "w") as f:
    f.writelines(lines)
PYEOF
  echo "==> Set ${key} in .env."
  # Settings are read once, at startup. Nothing is restarted automatically:
  # a restart would interrupt live conversations (#77).
  echo "==> Applies at the next start: a running application keeps its old value until you restart it (./start.sh --stop, then ./start.sh)."
}

# --- What runs, and stopping it (#77) ---
# A pid file alone is not enough to kill anything: a stale file can name a
# process that has since been given to something else. A process counts as ours
# only when it is alive AND its command line names what this script started.
pid_alive() {  # a process that has exited but was not reaped yet (state Z) is not alive
  local state
  kill -0 "$1" 2>/dev/null || return 1
  state="$(ps -p "$1" -o stat= 2>/dev/null | tr -d ' ')"
  [ -n "$state" ] && [ "${state:0:1}" != "Z" ]
}

pid_is() {  # pid_is FILE PATTERN -> 0 when FILE holds a live pid whose command matches PATTERN
  local file="$1" pattern="$2" pid
  [ -f "$file" ] || return 1
  pid="$(cat "$file" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  pid_alive "$pid" || return 1
  ps -p "$pid" -o command= 2>/dev/null | grep -q -- "$pattern"
}

http_code() {  # http_code URL -> status code, 000 when nothing answers
  curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null || true
}

load_env_if_present() {
  if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
}

docker_running_container() {  # prints the id of this project's running channelagent container
  command -v docker >/dev/null 2>&1 || return 1
  docker compose ps --status running -q channelagent 2>/dev/null | head -n 1 | grep .
}

show_status() {
  load_env_if_present
  local llama_port="${LLAMA_PORT:-8080}" api_port="${API_SERVER_PORT:-8700}" code container
  echo "==> ChannelAgent status"

  if ! command -v docker >/dev/null 2>&1; then
    echo "  app (container)  : docker not available"
  elif container="$(docker_running_container)"; then
    echo "  app (container)  : running (${container:0:12})"
  else
    echo "  app (container)  : not running"
  fi

  if pid_is .app.pid "app.main"; then
    echo "  app (native)     : running (pid $(cat .app.pid))"
  else
    echo "  app (native)     : not running"
  fi

  if [ -z "${API_SERVER_KEY:-}" ]; then
    echo "  Admin API        : disabled (API_SERVER_KEY is not set)"
  else
    code="$(http_code "http://127.0.0.1:${api_port}/users")"
    # 401 (no key sent) means the API is up and refusing, which is what it should do.
    case "$code" in
      200|401|429) echo "  Admin API        : up on 127.0.0.1:${api_port} (HTTP ${code})" ;;
      *) echo "  Admin API        : down on 127.0.0.1:${api_port}" ;;
    esac
  fi

  code="$(http_code "http://localhost:${llama_port}/health")"
  if [ "$code" = "200" ]; then
    if pid_is .llama-server.pid "llama-server"; then
      echo "  llama-server     : up on port ${llama_port} (pid $(cat .llama-server.pid), started by start.sh)"
    else
      echo "  llama-server     : up on port ${llama_port} (not started by start.sh)"
    fi
  else
    echo "  llama-server     : down on port ${llama_port}"
  fi
}

stop_pid_file() {  # stop_pid_file LABEL FILE PATTERN
  local label="$1" file="$2" pattern="$3" pid waited=0
  if pid_is "$file" "$pattern"; then
    pid="$(cat "$file")"
    kill "$pid"
    while pid_alive "$pid" && [ "$waited" -lt 30 ]; do
      sleep 0.5
      waited=$((waited + 1))
    done
    if pid_alive "$pid"; then
      echo "!! ${label} (pid ${pid}) did not stop within 15 s; it was sent SIGTERM only." >&2
      return 1
    fi
    rm -f "$file"
    echo "==> ${label} stopped (pid ${pid})."
  elif [ -f "$file" ]; then
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && pid_alive "$pid"; then
      echo "!! ${file} names pid ${pid}, which is not ${label} (its command line does not match): left alone." >&2
    else
      rm -f "$file"
      echo "==> ${label}: stale ${file} removed (no such process)."
    fi
  else
    echo "==> ${label}: not started by start.sh, nothing to stop."
  fi
}

stop_things() {
  local also_llama=0 status=0
  case "${1:-}" in
    "") ;;
    --all) also_llama=1 ;;
    *) echo "Usage: ./start.sh --stop [--all]" >&2; exit 1 ;;
  esac
  load_env_if_present

  stop_pid_file "native app" .app.pid "app.main" || status=1

  if command -v docker >/dev/null 2>&1 && docker_running_container >/dev/null; then
    echo "==> Stopping the container (docker compose stop channelagent)."
    docker compose stop channelagent || status=1
  else
    echo "==> app (container): not running."
  fi

  if [ "$also_llama" = "1" ]; then
    stop_pid_file "llama-server" .llama-server.pid "llama-server" || status=1
  else
    echo "==> llama-server left as it is (./start.sh --stop --all also stops the one this script started)."
  fi
  return "$status"
}

case "${1:-}" in
  --show-config)
    show_config
    exit 0
    ;;
  --set)
    set_config "${2:-}"
    exit 0
    ;;
  --status)
    show_status
    exit 0
    ;;
  --stop)
    stop_things "${2:-}"
    exit $?
    ;;
esac

MODE="docker"
case "${1:-}" in
  --native) MODE="native" ;;
  --admin) MODE="admin" ;;
  --restore) MODE="restore" ;;
  --rekey) MODE="rekey" ;;
esac

echo "==> ChannelAgent start.sh (mode: $MODE)"

# --- 1. .env must exist ---
if [ ! -f .env ]; then
  echo "!! No .env found. Copying .env.example — fill in real values before running the app." >&2
  create_env_from_example
fi
warn_if_env_is_shared

if ! grep -q "^ENCRYPTION_KEY=.\+" .env; then
  echo "!! ENCRYPTION_KEY is missing or empty in .env — the app will refuse to start without it." >&2
  echo "!! Generate one with: python3 -c \"import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\"" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

setup_venv() {
  if [ ! -d .venv ]; then
    echo "==> Creating virtualenv (.venv)"
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  echo "==> Installing dependencies"
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
}

# --- Admin console: pure DB/CLI, no llama-server needed at all ---
if [ "$MODE" = "admin" ]; then
  setup_venv
  exec python3 -m app.admin.cli
fi

# --- Rotate ENCRYPTION_KEY (#78): the guided sequence, application stopped ---
# `.env` was just sourced, which exported the OLD ENCRYPTION_KEY: the tool must
# read the key from the file and never from the environment, so it is removed.
if [ "$MODE" = "rekey" ]; then
  setup_venv
  shift
  exec env -u ENCRYPTION_KEY -u OLD_ENCRYPTION_KEY python3 -m app.admin.rekey_guided "$@"
fi

# --- Restore a backup: same venv, no llama-server, the application must be stopped ---
if [ "$MODE" = "restore" ]; then
  setup_venv
  shift
  exec python3 -m app.admin.restore "$@"
fi

# --- 2. Native llama-server: reuse it if running, start it if not (macOS only) ---
LLAMA_PORT="${LLAMA_PORT:-8080}"
if [ "$(uname -s)" = "Darwin" ]; then
  if curl -sf --max-time 2 "http://localhost:${LLAMA_PORT}/health" >/dev/null 2>&1; then
    echo "==> llama-server already running on localhost:${LLAMA_PORT}."
  elif [ -n "${LLAMA_SERVER_BIN:-}" ] && [ -x "${LLAMA_SERVER_BIN}" ] \
       && [ -n "${MODEL_FILE:-}" ] && [ -f "${MODELS_DIR:-}/${MODEL_FILE}" ]; then
    echo "==> llama-server not running — starting it (loading the model can take a while)."
    mkdir -p logs
    nohup "${LLAMA_SERVER_BIN}" \
      --port "${LLAMA_PORT}" \
      --host 127.0.0.1 \
      --model "${MODELS_DIR}/${MODEL_FILE}" \
      --ctx-size "${LLAMA_CTX_SIZE:-65536}" \
      -ngl 99 \
      --jinja \
      --flash-attn on \
      -ctk q8_0 \
      -ctv q8_0 \
      --predict 4096 \
      --repeat-penalty 1.1 \
      --skip-chat-parsing \
      > logs/llama-server.log 2>&1 &
    echo $! > .llama-server.pid
    echo "==> Waiting for it to become healthy (pid $(cat .llama-server.pid), log: logs/llama-server.log)..."
    ready=0
    for _ in $(seq 1 150); do
      if curl -sf --max-time 2 "http://localhost:${LLAMA_PORT}/health" >/dev/null 2>&1; then
        ready=1
        break
      fi
      sleep 2
    done
    if [ "$ready" = "1" ]; then
      echo "==> llama-server is up. It keeps running after this script exits — stop it with:"
      echo "==>   kill \$(cat .llama-server.pid)"
    else
      echo "!! llama-server did not become healthy in time — check logs/llama-server.log" >&2
      exit 1
    fi
  else
    echo "!! llama-server is not reachable on localhost:${LLAMA_PORT}, and LLAMA_SERVER_BIN /" >&2
    echo "!! MODELS_DIR / MODEL_FILE are not all set to valid paths in .env, so it can't be" >&2
    echo "!! started automatically. Set those three (see .env.example), or start it yourself —" >&2
    echo "!! reference: ../Hermes/macos-arm64/scripts/run-llama-server.sh" >&2
    exit 1
  fi
fi

# --- 3. Hand off to the selected mode ---
if [ "$MODE" = "docker" ]; then
  # The container runs as uid 10001, not root (#70). If ./data does not exist, Docker
  # creates it owned by root and the application then cannot write to it: create it
  # here, as the current user, first. On Linux the directory must also belong to
  # uid 10001 (Docker Desktop on macOS and Windows maps ownership by itself).
  mkdir -p data
  if [ "$(uname -s)" = "Linux" ] && [ "$(stat -c %u data 2>/dev/null || echo 10001)" != "10001" ]; then
    echo "!! data/ is not owned by uid 10001, the user the container runs as." >&2
    echo "!! Run once: sudo chown -R 10001:10001 data" >&2
  fi
  echo "==> Starting the container (docker compose up --build)."
  exec docker compose up --build
fi

# --- native mode ---
setup_venv

# Running outside Docker: host.docker.internal does not resolve here.
# Override regardless of what .env says, so --native doesn't silently
# fail to reach the LLM gateway.
export LLAMA_SERVER_URL="http://localhost:${LLAMA_PORT}"
echo "==> Native mode: LLAMA_SERVER_URL overridden to ${LLAMA_SERVER_URL}"

echo "==> Starting app/main.py natively."
# `exec` keeps this pid: --status and --stop find the process through it (#77).
echo $$ > .app.pid
exec python3 -m app.main
