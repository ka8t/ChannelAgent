#!/usr/bin/env bash
# #60: the TLS proxy overlay in a sandbox copy of the project (own .env, own ports).
# Needs the machine's LAN address for the "not reachable from the LAN" checks.
. "$(dirname "$0")/_lib.sh"
SB="$(mktemp -d)"; P=catls-rehearsal; API_PORT="$(free_port)"; TLS_PORT="$(free_port)"
LAN="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | cut -d' ' -f1)"
compose() { (cd "$SB" && TLS_PORT="$TLS_PORT" docker compose -p "$P" -f docker-compose.yml -f docker-compose.tls.yml "$@"); }
cleanup() { compose down -v >/dev/null 2>&1; docker rmi "${P}-channelagent" caddy:2-alpine >/dev/null 2>&1; rm -rf "$SB"; }
trap cleanup EXIT
cp -R "$REPO"/{Dockerfile,docker-compose.yml,docker-compose.tls.yml,docker,alembic,alembic.ini,requirements.txt,app} "$SB"/
mkdir -p "$SB/data"   # else Docker creates it root-owned and the uid 10001 application cannot write (#70)
API_KEY="$(openssl rand -hex 32)"
printf 'ENCRYPTION_KEY=%s\nAPI_SERVER_KEY=%s\nAPI_SERVER_PORT=%s\nTELEGRAM_BOT_TOKEN=\nEMAIL_IMAP_HOST=\n' \
  "$(fernet_key)" "$API_KEY" "$API_PORT" > "$SB/.env"; chmod 600 "$SB/.env"
compose up -d --build >/dev/null 2>&1
# Wait until the proxy reaches the application (anything but 502/000 from the proxy).
for _ in $(seq 1 30); do
  code="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 3 "https://localhost:$TLS_PORT/users")"
  [ "$code" = "401" ] && break; sleep 2
done
compose cp tls-proxy:/data/caddy/pki/authorities/local/root.crt "$SB/root.crt" >/dev/null 2>&1
c() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$@"; echo " exit=$?"; }
echo "HTTPS no key       : $(c --cacert "$SB/root.crt" "https://localhost:$TLS_PORT/users")"
echo "HTTPS right key    : $(c --cacert "$SB/root.crt" -H "Authorization: Bearer $API_KEY" "https://localhost:$TLS_PORT/users")"
echo "HTTPS no --cacert  : $(c "https://localhost:$TLS_PORT/users")"
echo "plain HTTP         : $(c "http://localhost:$TLS_PORT/users")"
echo "LAN https          : $(c --cacert "$SB/root.crt" --resolve "localhost:$TLS_PORT:$LAN" "https://localhost:$TLS_PORT/users")"
echo "LAN API port       : $(c "http://$LAN:$API_PORT/users")"
TLS_BIND_ADDRESS=0.0.0.0 compose up -d >/dev/null 2>&1; sleep 4
echo "control 0.0.0.0    : $(c --cacert "$SB/root.crt" --resolve "localhost:$TLS_PORT:$LAN" "https://localhost:$TLS_PORT/users")"
