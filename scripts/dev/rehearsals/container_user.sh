#!/usr/bin/env bash
# #70: the container does not run as root. Prints the uid, then boots the image on
# (A) a fresh named volume, (B) a consistent copy of the real data, (C) a data
# directory owned by root (tmpfs stand-in for a Linux bind mount) and by 10001.
. "$(dirname "$0")/_lib.sh"
IMAGE=channelagent-rehearsal-uid; SB="$(mktemp -d)"
cleanup() { docker rm -f ca-r-a ca-r-b ca-r-c1 ca-r-c2 >/dev/null 2>&1; docker rmi "$IMAGE" >/dev/null 2>&1
            docker volume rm ca-r-fresh >/dev/null 2>&1; rm -rf "$SB"; }
trap cleanup EXIT
docker build -q -t "$IMAGE" "$REPO" >/dev/null
echo "id: $(docker run --rm --entrypoint id "$IMAGE")"
FRESH="$(fernet_key)"
run() { docker run -d --name "$1" -e "ENCRYPTION_KEY=$FRESH" -e TELEGRAM_BOT_TOKEN= -e EMAIL_IMAP_HOST= \
          --health-interval=5s --health-start-period=0s "${@:2}" "$IMAGE" >/dev/null; }
docker volume create ca-r-fresh >/dev/null
run ca-r-a -v ca-r-fresh:/app/data
echo "A fresh volume      : $(wait_for_health ca-r-a 60)"
docker exec ca-r-a python -c "import sqlite3;print('  revision', sqlite3.connect('/app/data/channelagent.db').execute('select version_num from alembic_version').fetchone()[0])"
copy_real_data "$SB/data"
run ca-r-b -v "$SB/data:/app/data"
echo "B real-data copy    : $(wait_for_health ca-r-b 60)"
docker run -d --name ca-r-c1 -e "ENCRYPTION_KEY=$FRESH" -e TELEGRAM_BOT_TOKEN= -e EMAIL_IMAP_HOST= \
  --tmpfs /app/data:uid=0,gid=0,mode=755 "$IMAGE" >/dev/null; sleep 8
echo "C dir owned by root : $(docker ps -a --filter name=ca-r-c1 --format '{{.Status}}')"
run ca-r-c2 --tmpfs /app/data:uid=10001,gid=10001,mode=755
echo "C dir owned by 10001: $(wait_for_health ca-r-c2 60)"
