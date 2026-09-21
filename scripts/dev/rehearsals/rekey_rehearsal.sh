#!/usr/bin/env bash
# #78: `./start.sh --rekey` end to end on a consistent copy of the REAL data (real key,
# sandbox files only), then an independent read of the result. The real .env and data/
# are never written. No key is printed. Needs no Docker (PATH has none, so the
# "application is running" container check cannot see the owner's container).
. "$(dirname "$0")/_lib.sh"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
umask 077
cp "$REPO"/{start.sh,.env.example,requirements.txt,alembic.ini} "$SB"/; cp -R "$REPO"/{app,alembic} "$SB"/
ln -s "$REPO/.venv" "$SB/.venv"; copy_real_data "$SB/data"; cp "$REPO/.env" "$SB/.env"; chmod 600 "$SB/.env"
python3 - "$SB/.env" "$(free_port)" <<'PY'
import sys
path, port = sys.argv[1], sys.argv[2]
drop = ("API_SERVER_PORT=", "TELEGRAM_BOT_TOKEN=", "EMAIL_PASSWORD=", "DATABASE_URL=", "CHECKPOINT_DB_PATH=")
lines = [l for l in open(path).read().splitlines() if not l.startswith(drop)]
open(path, "w").write("\n".join(lines + [f"API_SERVER_PORT={port}", "TELEGRAM_BOT_TOKEN=", "EMAIL_PASSWORD="]) + "\n")
PY
cd "$SB"
printf 'ROTATE\n' | PATH=/usr/bin:/bin:/usr/sbin ./start.sh --rekey > run.out 2>&1; echo "start.sh exit=$?"
grep -E "to re-encrypt|value\(s\) re-encrypted|cannot decrypt|Refused" run.out
"$PY" - <<'PY'
import pathlib, sqlite3
from cryptography.fernet import Fernet, InvalidToken

def key(path):
    return next(l.split("=", 1)[1] for l in pathlib.Path(path).read_text().splitlines()
                if l.startswith("ENCRYPTION_KEY="))

new, old = key(".env"), key(".env.pre-rekey")
spec = [("action_logs", "text"), ("access_requests", "first_message_text"),
        ("channel_identities", "raw_address"), ("admin_events", "details")]
con = sqlite3.connect("data/channelagent.db")
vals = [v for t, c in spec for (v,) in con.execute(f'select "{c}" from "{t}" where "{c}" is not null')]

def readable(k):
    f, n = Fernet(k.encode()), 0
    for v in vals:
        try:
            f.decrypt(v.encode()); n += 1
        except InvalidToken:
            pass
    return n

out = pathlib.Path("run.out").read_text()
print("application values:", len(vals), "| new key reads:", readable(new), "| old key reads:", readable(old))
print("old key in output:", old in out, "| new key in output:", new in out)
print("files containing the old key:", sorted(str(p) for p in pathlib.Path(".").rglob("*")
      if p.is_file() and not p.is_symlink() and ".venv" not in p.parts and old.encode() in p.read_bytes()))
PY
