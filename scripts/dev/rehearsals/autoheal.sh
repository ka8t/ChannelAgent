#!/usr/bin/env bash
# #89: docker-compose.autoheal.yml restarts a frozen (unhealthy) application container.
# Sandbox copy, own project name, healthcheck shortened by a sandbox-only override.
. "$(dirname "$0")/_lib.sh"
SB="$(mktemp -d)"; P=caheal-rehearsal
compose() { (cd "$SB" && docker compose -p "$P" -f docker-compose.yml -f docker-compose.autoheal.yml -f override.yml "$@"); }
cleanup() { compose down -v >/dev/null 2>&1; docker rmi "${P}-channelagent" willfarrell/autoheal:latest >/dev/null 2>&1; rm -rf "$SB"; }
trap cleanup EXIT
cp -R "$REPO"/{Dockerfile,docker-compose.yml,docker-compose.autoheal.yml,alembic,alembic.ini,requirements.txt,app} "$SB"/
mkdir "$SB/data"
FRESH="$(fernet_key)"
printf 'ENCRYPTION_KEY=%s\nTELEGRAM_BOT_TOKEN=\nEMAIL_IMAP_HOST=\n' "$FRESH" > "$SB/.env"; chmod 600 "$SB/.env"
cat > "$SB/override.yml" <<'YML'
services:
  channelagent:
    ports: !reset []
    healthcheck:
      test: ["CMD", "python", "-m", "app.health"]
      interval: 5s
      timeout: 5s
      retries: 1
      start_period: 0s
YML
compose up -d --build >/dev/null 2>&1
CID="$(compose ps -q channelagent)"
status() { docker inspect -f '{{.State.Health.Status}}' "$CID"; }
started() { docker inspect -f '{{.State.StartedAt}}' "$CID"; }
for _ in $(seq 1 30); do [ "$(status)" = healthy ] && break; sleep 2; done
echo "before freeze: $(status), started at $(started)"
FIRST="$(started)"; T0=$(date +%s)
docker kill --signal=SIGSTOP "$CID" >/dev/null
seen_unhealthy=""
for _ in $(seq 1 60); do
  [ "$(status)" = unhealthy ] && [ -z "$seen_unhealthy" ] && seen_unhealthy=$(( $(date +%s) - T0 ))
  [ "$(started)" != "$FIRST" ] && break; sleep 2
done
echo "unhealthy after ${seen_unhealthy:-never}s; restarted after $(( $(date +%s) - T0 ))s (StartedAt changed: $([ "$(started)" != "$FIRST" ] && echo yes || echo no))"
for _ in $(seq 1 30); do [ "$(status)" = healthy ] && break; sleep 2; done
echo "after restart: $(status)"
docker logs "${P}-autoheal-1" 2>&1 | grep -i "unhealthy\|restart" | tail -2 | cut -c1-140
