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

Session paused 2026-09-18 (resuming after 2026-09-20). All P0-critical
work is done and verified (encrypted database, Auth Node, LangGraph
orchestrator, Docker packaging including a real production VPS
topology test). The Admin API (epic #5) and the agent/request/logging
mechanics with an interactive console (`./start.sh --admin`, epic #35)
are both done. Telegram (#27) and Email (#28) adapters are live and
verified with real end-to-end round trips; Matrix (#29) is not yet
implemented, blocked on real credentials. 378 automated tests, 0
failing. Full picture, always current: `gh issue list --repo
ka8t/ChannelAgent`; `CLAUDE.md`'s "Session paused" entry at the top has
the exact resume checklist.

## Prerequisites

- Python 3.11+
- Docker
- On macOS: a local `llama-server` process serving an LLM on port
  8080. ChannelAgent does not run its own inference server; it calls
  out to this one (native on Mac for development, a containerized
  `llama-server` in production — see `docs/ARCHITECTURE.md`).

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
- `EMAIL_TRIGGER_TAG` — default `[agent]`. The email mailbox is shared
  with ordinary mail (website contact form, customer questions), so the
  bot only reads and answers messages whose **subject contains this
  tag**, for example `[agent] what is on my list today?`. Every other
  message is left untouched and unread. Replies keep the tag, so a
  conversation continues without retyping it. Rules and the planned move
  to a dedicated bot mailbox
  ([#42](https://github.com/ka8t/ChannelAgent/issues/42)):
  `docs/ARCHITECTURE.md`, section "Email on a shared mailbox".
- `EMAIL_AGENT_FOLDER` — default `INBOX.Agent`. A handled agent message
  is moved here so it leaves the `INBOX` that humans read (the folder is
  created on first use). The `.` separator is the OVH/Dovecot layout, use
  your provider's otherwise. Empty leaves messages in the `INBOX`.
  Nothing is ever deleted or purged automatically.
- `API_SERVER_KEY`, `API_SERVER_PORT`, `API_SERVER_HOST`,
  `API_BIND_ADDRESS` — the Admin API. It stays off until `API_SERVER_KEY`
  is set (at least 16 characters, `openssl rand -hex 32`), and it is
  reachable **from the local machine only** by default, because it
  serves decrypted conversations over plain HTTP: `API_SERVER_HOST`
  (native run) and `API_BIND_ADDRESS` (the address Docker publishes the
  port on) both default to `127.0.0.1`. To administer remotely use an SSH
  tunnel or a TLS reverse proxy, see `docs/ARCHITECTURE.md` ("Admin API
  exposure").
- `MIGRATION_BACKUPS_KEEP` — default 5. Before a migration changes an
  existing database, it is copied into `backups/` next to it and the copy is
  verified; if that fails the migration does not run. `0` turns it off.
  Restore instructions: `docs/ARCHITECTURE.md` ("Database and migrations").
- `CHECKPOINT_DB_PATH` — where conversations are stored so they survive a
  restart. Empty (the default) means `checkpoints.db` next to the main
  database, inside the Docker volume. The content is encrypted with
  `ENCRYPTION_KEY`. Back up `checkpoints.db*` (three files, WAL mode) with
  the main database.
- `LLAMA_SERVER_URL` — where the LLM gateway is reachable. Defaults to
  `http://host.docker.internal:8080` (the container reaching the Mac
  host's native `llama-server`; see `docs/ARCHITECTURE.md`).

`.env` is git-ignored and must never be committed. `ENCRYPTION_KEY`
must never be stored in the database either — see
`app/security/encryption.py`.

Instead of editing `.env` by hand, `start.sh` can read and change any
of these variables directly:

```bash
./start.sh --show-config          # list every variable, secrets masked
./start.sh --set LLAMA_PORT=8081  # add or update one variable in .env
```

## Start

Start `llama-server` natively on the Mac first (see Prerequisites and
Troubleshooting below), then:

```bash
docker compose up --build
```

`app/main.py` boots configuration, the database and the first admin
(from `TELEGRAM_ALLOWED_USERS`, on an empty database only), then starts
each part that is configured and logs which ones are disabled: the
Telegram adapter (needs `TELEGRAM_BOT_TOKEN`), the Email adapter (needs
`EMAIL_IMAP_HOST`, `EMAIL_USERNAME` and `EMAIL_PASSWORD`) and the Admin
API (needs `API_SERVER_KEY`). The Matrix adapter is not implemented yet.

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

## Production deployment (VPS)

`docker-compose.prod.yml` adds a containerized `llama-server` on the
internal Docker network instead of relying on the Mac's native one —
see `docs/ARCHITECTURE.md`'s "Compute topology" for why a containerized
`llama-server` was chosen over Ollama/vLLM. Use it alongside the base
compose file, not instead of it:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Requires, set in `.env`:

- `MODELS_DIR` — directory containing the `.gguf` model file.
- `LLAMA_SERVER_BIN_DIR` — directory containing a prebuilt Linux
  `llama-server` binary (obtaining one is a separate concern from this
  topology — the legacy Hermes project's
  `linux-x86_64-vps/scripts/download-prebuilt-llama-server.sh` is a
  working reference if useful).
- `MODEL_FILE`, already used by the Mac dev setup.
- `LLAMA_THREADS` (default 4) — CPU thread count; there is no GPU
  offload flag in this topology, unlike the Mac's Metal setup.

`docker compose -f docker-compose.yml -f docker-compose.prod.yml
config` fails with a clear message naming whichever of these isn't set
— confirmed directly, not just documented.

This has been verified as far as this development environment allows:
the compose file's merge resolves correctly (confirmed via `config`,
`LLAMA_SERVER_URL` correctly becomes `http://llama-server:8080` and
`channelagent` correctly waits on `llama-server`'s healthcheck) and
`docker/llama-server.Dockerfile` builds. **Not yet verified**: an
actual inference round trip through this topology — that needs a real
Linux `llama-server` binary and a Linux Docker host, neither available
in this environment (the Mac's own `llama-server` binary is macOS-only
and won't run in this container).

## Administering users, requests and agents

The console (`./start.sh --admin`) and the Admin API do the same things
through the same code: list and detail users, create, activate and
deactivate them, add and remove channel identities, grant and revoke
permissions, approve or deny access requests (`GET /requests`,
`POST /requests/{id}/approve|deny`), and create, rename and activate or
deactivate any user's agents (`/users/{id}/agents`, `/agents/{id}`). The
full table is in `docs/ARCHITECTURE.md` ("Admin API and console over one
service layer"). On Telegram a user with several agents chooses with `/agent` (list) and
`/agent <name>` (switch); an admin can set it per identity from the console
or `PUT /users/{id}/channels/{identity_id}/agent`. Deleting a user who has
history is refused unless you
purge (`DELETE /users/{id}?purge=true`, or type `PURGE` in the console).

## Searching the audit trail

Every message the bot receives or sends is logged (text encrypted at
rest). Search it from the admin console (`./start.sh --admin`, menu 4,
blank answer = no filter) or from the Admin API:

```bash
curl -H "Authorization: Bearer $API_SERVER_KEY" \
  "http://localhost:8700/logs?user_id=1&channel=email&keyword=invoice&since=2026-09-01&limit=20"
```

Filters: `user_id`, `agent_id`, `channel`, `direction`, `status` (`ok`, `failed`, `denied`), `since`
(inclusive), `until` (exclusive), `keyword` (case-insensitive, matched
on the decrypted text), `limit` (1 to 500), `offset`. Both front ends
call the same function, details in `docs/ARCHITECTURE.md`
("Audit trail and log search").

The same console (menu 5) and API (`GET /storage`) also give a storage
overview: database size, row count per table, and the time span of the
audit trail.

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

## Updating dependencies

The versions are locked: `requirements.txt` (what the image, CI and
`start.sh` install) and `requirements-dev.txt` (what CI installs, runtime
plus test tools) hold exact pins for every package, including the indirect
ones. Do not edit them: change `requirements.in` / `requirements-dev.in`
(the loose lists of direct dependencies) and regenerate.

```bash
scripts/update_requirements.sh --keep   # after editing an .in file: keep current pins
scripts/update_requirements.sh          # move everything to the newest versions
```

The script resolves inside `python:3.12-slim`, the interpreter of the image
and of CI, so the result does not depend on the Python installed on your
machine. Review the diff like code, then run `pytest` and the audit:

```bash
pip-audit -r requirements.txt --no-deps --disable-pip   # exit 0 = no known vulnerability
```

CI runs the same audit and fails on any known vulnerability. A reviewed
exception is added to that CI step as `--ignore-vuln <ID>` with a comment
saying why and until when. Dependabot opens one grouped update pull request
per week (`.github/dependabot.yml`).

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
