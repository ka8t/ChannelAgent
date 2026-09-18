#!/usr/bin/env bash
# Guided entry point for local development, adapted from Hermes's own
# start.sh (which dispatched to a platform-specific provisioning script).
# ChannelAgent targets a single Linux Docker container in every
# environment, so there is no per-platform dispatch here — this script
# instead prepares the local Python dev environment and checks the one
# genuinely platform-specific dependency: the native llama-server running
# on the Mac host (see docs/ARCHITECTURE.md, "Compute topology").
#
# Once app/main.py and the Dockerfile exist (see docs/ARCHITECTURE.md
# "Status"), this script will build/run the container instead. Until
# then it sets up and validates a local dev environment.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "==> ChannelAgent local setup"

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

# --- 2. Python virtualenv ---
if [ ! -d .venv ]; then
  echo "==> Creating virtualenv (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "==> Installing dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# --- 3. Local LLM gateway reachability (macOS dev only) ---
if [ "$(uname -s)" = "Darwin" ]; then
  echo "==> Checking llama-server on http://localhost:8080"
  if curl -sf --max-time 2 http://localhost:8080/health >/dev/null 2>&1; then
    echo "==> llama-server is reachable."
  else
    echo "!! llama-server is not reachable on port 8080." >&2
    echo "!! ChannelAgent's Docker container reaches it via host.docker.internal:8080," >&2
    echo "!! but it must first be running natively on this Mac. See the legacy" >&2
    echo "!! Hermes setup at ../Hermes/macos-arm64/scripts/run-llama-server.sh for reference." >&2
  fi
fi

echo ""
echo "==> Environment ready."
echo "==> app/main.py and the Dockerfile are not implemented yet (see docs/ARCHITECTURE.md, Status)."
echo "==> Once they exist, this script will build and run the container instead of stopping here."
