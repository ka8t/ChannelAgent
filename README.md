# ChannelAgent

A 100% local, multi-user, multi-channel agentic system built on
[LangGraph](https://langchain-ai.github.io/langgraph/), packaged as a
Linux Docker container. It replaces the Hermes Agent orchestrator
(legacy project, not part of this repository), moving user
authorization from static `.env` allow-lists to a proper encrypted
database + API layer.

Full architecture, diagrams, and the audit of the legacy system this
project replaces: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
Project conventions and the running decision log: [`CLAUDE.md`](CLAUDE.md).

## Status

The P0 milestone is done: encrypted database, Auth Node, LangGraph
orchestrator, and Docker packaging all exist and are verified — see
`CLAUDE.md`'s "P0 milestone" entry for exactly what was tested. There
are no channel adapters yet (Telegram/Email/Matrix — epic #6) and no
Admin API yet (epic #5), so nothing routes a real message end-to-end
on its own; `app/main.py` currently just boots the app and the
database. Full picture: `gh issue list --repo ka8t/ChannelAgent`.

## Prerequisites

- Python 3.11+
- Docker
- On macOS: a local `llama-server` process serving an LLM on port
  8080. ChannelAgent does not run its own inference server; it calls
  out to this one (native on Mac for development, an
  Ollama/vLLM container in production — see `docs/ARCHITECTURE.md`).

## Install

```bash
git clone <this-repo>
cd ChannelAgent
./start.sh
```

`start.sh` copies `.env.example` to `.env` if missing, creates a
Python virtualenv, installs `requirements.txt`, and (on macOS) checks
that `llama-server` is reachable on `localhost:8080`.

## Configure

Copy `.env.example` to `.env` (done automatically by `start.sh` if
missing) and fill in:

- `ENCRYPTION_KEY` — required. A Fernet key (32 url-safe
  base64-encoded bytes), used to encrypt sensitive fields (emails,
  Matrix tokens, other personal metadata) before they are written to
  the database. Generate one with:
  ```bash
  python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
  ```
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_ALLOWED_USERS` — for the Telegram
  adapter.
- `EMAIL_*` / `MATRIX_*` — for the Email and Matrix/Element adapters,
  optional.
- `LLAMA_SERVER_URL` — where the LLM gateway is reachable. Defaults to
  `http://host.docker.internal:8080` (the container reaching the Mac
  host's native `llama-server`; see `docs/ARCHITECTURE.md`).

`.env` is git-ignored and must never be committed. `ENCRYPTION_KEY`
must never be stored in the database either — see
`app/security/encryption.py`.

## Start

Start `llama-server` natively on the Mac first (see Prerequisites and
Troubleshooting below), then:

```bash
docker compose up --build
```

`app/main.py` boots configuration and the database and stays running;
there are no channel adapters wired in yet (see Status), so it doesn't
do anything beyond that on its own.

`start.sh` still exists for local (non-Docker) development: it copies
`.env.example` to `.env` if missing, creates a Python virtualenv,
installs `requirements.txt`, and (on macOS) checks that `llama-server`
is reachable on `localhost:8080`.

## Verify

Confirm the encryption layer loads correctly:

```bash
source .venv/bin/activate
python3 -c "from app.security.encryption import encrypt_value, decrypt_value; t = encrypt_value('test'); assert decrypt_value(t) == 'test'; print('encryption OK')"
```

Confirm the container reaches a real `llama-server` running on the Mac
host (verified 2026-09-18 — see issue #20 for the full record):

```bash
# with llama-server already running on localhost:8080
docker compose run --rm channelagent python3 -c "
import asyncio
from app.db.models import Channel
from app.graph import run_turn
print(asyncio.run(run_turn(Channel.TELEGRAM, 'debug', 'Reply with exactly the word: pong')))
"
```

This should print `pong` (or close to it, depending on the model) —
proof the container reached `host.docker.internal:8080` and got a real
completion back, not just that the TCP port is open.

## Database migrations

Schema changes are tracked with [Alembic](https://alembic.sqlalchemy.org/)
(`alembic/versions/`), not `Base.metadata.create_all`. `app/db/session.py`'s
`init_db()` runs `alembic upgrade head` at every startup — normal use
never requires a manual migration step.

When you change a model in `app/db/models.py`:

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "describe the change"
```

Then **read the generated file in `alembic/versions/`** before
committing it — autogenerate gets the SQL right but not always the
Python: it has already once emitted a reference to a custom column
type (`app.db.types.EncryptedString`) without importing it, which
would fail at migration time with a `NameError` if applied as-is.
Apply it locally to confirm it works:

```bash
alembic upgrade head
```

`alembic.ini`'s `sqlalchemy.url` is a placeholder — `alembic/env.py`
overrides it from `.env`'s `DATABASE_URL` at runtime (via
`app.config.get_settings()`), the same setting the application itself
uses, so a migration can never accidentally target a different
database than the app runs against.

## Troubleshooting

- **`ENCRYPTION_KEY is missing or empty`** (from `start.sh` or
  `app/config.py`): generate one with the command under Configure
  above and set it in `.env`.
- **`llama-server is not reachable`** (macOS, from `start.sh`, or a
  connection error from the Verify command above): start it natively
  on the Mac host first — this project does not manage that process.
  The legacy repo's `../Hermes/macos-arm64/scripts/run-llama-server.sh`
  is a working reference invocation (binary path, model, and flags);
  it expects Hermes's own `.env`, so either run it from there or reuse
  just its `llama-server` command line with this project's `.env`
  values (`LLAMA_CTX_SIZE`, `MODEL_FILE`).
- **Fernet `ValueError: Fernet key must be 32 url-safe base64-encoded
  bytes`**: `ENCRYPTION_KEY` is in the wrong format — it must not be a
  hex string (e.g. a SHA-256 digest); it must be the base64 output of
  `Fernet.generate_key()` or the equivalent shown under Configure.
- **`telegram.error.Conflict: terminated by other getUpdates
  request`**: Telegram allows only one long-polling connection per bot
  token. `TELEGRAM_BOT_TOKEN` is deliberately reused from the legacy
  Hermes project (same physical bot). Hermes's local gateway
  (`ai.hermes.gateway`, a launchd service) has since been disabled on
  this Mac — see `CLAUDE.md`'s "Operational finding" note for the
  exact commands — but if Hermes is ever running anywhere else with
  this same token (e.g. redeployed on a VPS), stop it first, or the two
  will fight over the connection.

## Sources

- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [`cryptography`'s Fernet](https://cryptography.io/en/latest/fernet/)
