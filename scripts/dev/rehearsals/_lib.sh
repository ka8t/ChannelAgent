# Shared helpers for the rehearsal scripts. Source it: . scripts/dev/rehearsals/_lib.sh
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"

fernet_key() { "$PY" -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"; }
free_port() { python3 -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1])"; }

# wait_for_health CONTAINER SECONDS -> prints the final status (healthy, unhealthy, starting, ...)
wait_for_health() {
  local name="$1" limit="$2" waited=0 status=""
  while [ "$waited" -lt "$limit" ]; do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo gone)"
    [ "$status" = "healthy" ] && break
    sleep 2; waited=$((waited + 2))
  done
  echo "$status"
}

# copy_real_data DEST_DIR : consistent copy (sqlite .backup) of data/ into DEST_DIR, read-only on the source
copy_real_data() {
  mkdir -p "$1"
  sqlite3 "file:$REPO/data/channelagent.db?mode=ro" ".backup $1/channelagent.db"
  sqlite3 "file:$REPO/data/checkpoints.db?mode=ro" ".backup $1/checkpoints.db"
}
