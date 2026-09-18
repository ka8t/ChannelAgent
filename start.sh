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
# Both modes need a native llama-server running on this Mac first
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

MODE="docker"
if [ "${1:-}" = "--native" ]; then
  MODE="native"
fi

echo "==> ChannelAgent start.sh (mode: $MODE)"

# --- 1. .env must exist ---
if [ ! -f .env ]; then
  echo "!! No .env found. Copying .env.example — fill in real values before running the app." >&2
  cp .env.example .env
fi

if ! grep -q "^ENCRYPTION_KEY=.\+" .env; then
  echo "!! ENCRYPTION_KEY is missing or empty in .env — the app will refuse to start without it." >&2
  echo "!! Generate one with: python3 -c \"import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\"" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

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
  echo "==> Starting the container (docker compose up --build)."
  exec docker compose up --build
fi

# --- native mode ---
if [ ! -d .venv ]; then
  echo "==> Creating virtualenv (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Running outside Docker: host.docker.internal does not resolve here.
# Override regardless of what .env says, so --native doesn't silently
# fail to reach the LLM gateway.
export LLAMA_SERVER_URL="http://localhost:${LLAMA_PORT}"
echo "==> Native mode: LLAMA_SERVER_URL overridden to ${LLAMA_SERVER_URL}"

echo "==> Starting app/main.py natively."
exec python3 -m app.main
