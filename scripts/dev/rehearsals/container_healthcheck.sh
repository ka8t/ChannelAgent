#!/usr/bin/env bash
# #48: build the image, run it throwaway, expect `healthy`, freeze it, expect `unhealthy`.
. "$(dirname "$0")/_lib.sh"
IMAGE=channelagent-rehearsal-health; NAME=ca-rehearsal-health
trap 'docker rm -f "$NAME" >/dev/null 2>&1; docker rmi "$IMAGE" >/dev/null 2>&1' EXIT
docker build -q -t "$IMAGE" "$REPO" >/dev/null
FRESH="$(fernet_key)"
docker run -d --name "$NAME" -e "ENCRYPTION_KEY=$FRESH" -e TELEGRAM_BOT_TOKEN= \
  -e EMAIL_IMAP_HOST= --health-interval=5s --health-timeout=5s \
  --health-retries=1 --health-start-period=0s "$IMAGE" >/dev/null
echo "after start : $(wait_for_health "$NAME" 60)"
docker kill --signal=SIGSTOP "$NAME" >/dev/null
waited=0; status=healthy
while [ "$waited" -lt 120 ] && [ "$status" != unhealthy ]; do
  sleep 5; waited=$((waited + 5)); status="$(docker inspect -f '{{.State.Health.Status}}' "$NAME")"
done
echo "after freeze: $status (after ${waited}s)"
docker inspect -f '{{range .State.Health.Log}}{{.ExitCode}} {{.Output}}{{end}}' "$NAME" | tail -1
