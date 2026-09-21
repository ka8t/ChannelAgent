#!/usr/bin/env bash
# #91: the documented SSH tunnel to the Admin API, against a throwaway sshd container.
# The "host" is a container running sshd; the application runs in a second container
# that shares its network namespace, so 127.0.0.1:<API port> inside the host is the API,
# exactly like the loopback-only publishing of a real host. Needs Docker and ssh.
. "$(dirname "$0")/_lib.sh"
SB="$(mktemp -d)"; HOST=ca-r-sshhost; APP=ca-r-sshapp; IMAGE=channelagent-rehearsal-ssh
SSH_PORT="$(free_port)"; LOCAL_PORT="$(free_port)"; API_PORT="$(free_port)"; TUNNEL_PID=""
SSH_OPTS=(-i "$SB/id" -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=3)
cleanup() { [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null
            docker rm -f "$APP" "$HOST" >/dev/null 2>&1; docker rmi "$IMAGE" >/dev/null 2>&1; rm -rf "$SB"; }
trap cleanup EXIT
ssh-keygen -q -t ed25519 -N "" -f "$SB/id" >/dev/null
docker build -q -t "$IMAGE" "$REPO" >/dev/null
docker run -d --name "$HOST" -p "127.0.0.1:$SSH_PORT:22" -v "$SB/id.pub:/authorized_keys:ro" \
  python:3.12-slim sh -c 'apt-get update -qq && apt-get install -y -qq openssh-server >/dev/null \
  && mkdir -p /run/sshd /root/.ssh && cp /authorized_keys /root/.ssh/authorized_keys \
  && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys \
  && exec /usr/sbin/sshd -D -e -o PermitRootLogin=prohibit-password -o AllowTcpForwarding=yes' >/dev/null
API_KEY="$(openssl rand -hex 32)"; FRESH="$(fernet_key)"
docker run -d --name "$APP" --network "container:$HOST" -e "ENCRYPTION_KEY=$FRESH" \
  -e "API_SERVER_KEY=$API_KEY" -e "API_SERVER_PORT=$API_PORT" -e TELEGRAM_BOT_TOKEN= -e EMAIL_IMAP_HOST= "$IMAGE" >/dev/null
# The published port answers before sshd runs (apt install first): wait for a real login.
for _ in $(seq 1 90); do ssh "${SSH_OPTS[@]}" root@127.0.0.1 true 2>/dev/null && break; sleep 2; done
c() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$@"; }
echo "API port on the Mac itself (not published, must be refused): $(c "http://127.0.0.1:$API_PORT/users")"
ssh "${SSH_OPTS[@]}" -o ExitOnForwardFailure=yes -N -L "$LOCAL_PORT:127.0.0.1:$API_PORT" root@127.0.0.1 >/dev/null 2>&1 &
TUNNEL_PID=$!
for _ in $(seq 1 30); do nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null && break; sleep 1; done
echo "through the tunnel, no key   : $(c "http://127.0.0.1:$LOCAL_PORT/users")"
echo "through the tunnel, wrong key: $(c -H 'Authorization: Bearer wrong' "http://127.0.0.1:$LOCAL_PORT/users")"
echo "through the tunnel, right key: $(c -H "Authorization: Bearer $API_KEY" "http://127.0.0.1:$LOCAL_PORT/users")"
kill "$TUNNEL_PID"; TUNNEL_PID=""; sleep 1
echo "after the tunnel is closed   : $(c "http://127.0.0.1:$LOCAL_PORT/users")"
