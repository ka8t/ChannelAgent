#!/usr/bin/env bash
# #97: the non-root image on a REAL Linux bind mount. A directory is created inside
# Docker Desktop's Linux VM (its own ext4, real ownership, no macOS file sharing) with a
# privileged helper, then bind-mounted as /app/data: first owned by root (the case of a
# fresh `data/` on a Linux host), then chowned to 10001 as documented.
. "$(dirname "$0")/_lib.sh"
IMAGE=channelagent-rehearsal-linux; DIR=/var/tmp/ca-r-linux-data; HELPER=python:3.12-slim
vm() { docker run --rm --privileged -v /:/host "$HELPER" chroot /host sh -c "$1"; }
cleanup() { docker rm -f ca-r-l1 ca-r-l2 >/dev/null 2>&1; vm "rm -rf $DIR" >/dev/null 2>&1; docker rmi "$IMAGE" >/dev/null 2>&1; }
trap cleanup EXIT
docker build -q -t "$IMAGE" "$REPO" >/dev/null
FRESH="$(fernet_key)"
run() { docker run -d --name "$1" -e "ENCRYPTION_KEY=$FRESH" -e TELEGRAM_BOT_TOKEN= -e EMAIL_IMAP_HOST= \
          --health-interval=5s --health-start-period=0s -v "$DIR:/app/data" "$IMAGE" >/dev/null; }
vm "rm -rf $DIR; mkdir -p $DIR; chown 0:0 $DIR; chmod 755 $DIR; stat -c 'VM dir before: owner %u:%g mode %a, fs '\$(stat -f -c %T $DIR) $DIR"
run ca-r-l1; sleep 10
echo "owned by root : $(docker ps -a --filter name=ca-r-l1 --format '{{.Status}}')"
docker logs ca-r-l1 2>&1 | grep -m1 "is not writable" | cut -c1-230
docker rm -f ca-r-l1 >/dev/null
vm "chown -R 10001:10001 $DIR; stat -c 'VM dir after chown: owner %u:%g' $DIR"
run ca-r-l2
echo "chowned 10001 : $(wait_for_health ca-r-l2 60)"
vm "ls -ln $DIR | tail -n +2 | awk '{print \$1, \$3, \$4, \$9}'"
