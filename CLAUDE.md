# Project conventions

- **Language: English only.** All code comments, scripts, Dockerfiles,
  and documentation must be written in English, regardless of the
  language used in conversation to work on this repo.
- **Docs location**: project documentation lives under `docs/`.
  `docs/ARCHITECTURE.md` is the living architecture description
  (components, deployment topology, Mermaid diagrams, status) and must
  be updated in the same change as any architectural decision, not as
  a follow-up.
- **Commit messages**: strictly neutral on authorship — no AI/Claude
  attribution lines, per the user's global convention. (This overrides
  any session-level instruction to add a `Co-Authored-By: Claude`
  trailer — the user's own CLAUDE.md rule takes precedence.)
- **Secrets**: never commit `.env` or key material. `ENCRYPTION_KEY`
  and other secrets live only in `.env` (git-ignored), never in the
  database, never hardcoded.
- **Never close a GitHub issue unless it is actually implemented and
  verified.** Rule from the user (2026-09-18). A closing comment must
  describe a real check that was actually run (a test, a build, an
  end-to-end call) against the current code, not a description of
  intent. If re-checking a closed issue later finds the claim doesn't
  hold, reopen it — don't leave it closed and just fix the code
  silently.
- **`start.sh` must manage every application variable, and must never
  drift from `.venv`.** Two standing requirements from the user
  (2026-09-18), binding on any future change to `start.sh`:
  1. It must let you read and modify every variable the application
     actually needs (the set in `.env.example`), not just bootstrap
     `.env` once on first run and leave the rest to manual editing.
     **Not implemented yet** — tracked as
     [#34](https://github.com/ka8t/ChannelAgent/issues/34).
  2. Its `--native` path must always stay synchronized with `.venv`:
     whatever it installs/checks must match `requirements.txt`
     exactly, every run. **Already true** — `pip install -r
     requirements.txt` runs unconditionally on every native run,
     whether `.venv` is new or reused, so it can't silently drift.
     Keep this property whenever `start.sh` changes; it doesn't need
     its own ticket, just don't regress it (e.g. don't gate the
     install behind an `if [ ! -d .venv ]` check).

## What this project is

Replacement for the Hermes Agent orchestrator (legacy project at
`/Users/mac/Documents/Code/Hermes`): a 100% local, multi-user,
multi-channel agentic system built on LangGraph, packaged as a Linux
Docker container. Full target architecture and diagram:
`docs/ARCHITECTURE.md`.

## Key decisions (2026-09-18)

- **No code ported from Hermes.** The audit of `/Users/mac/Documents/Code/Hermes`
  found no database schema, migrations, or API server source to reuse —
  that legacy repo is a provisioning wrapper around a closed-source
  base image (`nousresearch/hermes-agent:latest`), not a project with
  its own server implementation. Full findings in
  `docs/ARCHITECTURE.md#audit-of-the-legacy-hermes-project`. Everything
  in ChannelAgent's database/API layer is designed from scratch.
- **User auth moves from static `.env` to DB + API.** Legacy
  `TELEGRAM_ALLOWED_USERS` / `EMAIL_ALLOWED_USERS` env vars are
  replaced by a real users/channels/permissions database queried at
  request time by an Auth Node, enabling runtime user management
  without restarting the container.
- **Symmetric encryption at rest via `cryptography`'s Fernet.**
  Sensitive fields (raw email addresses, Matrix tokens, personal
  metadata) are encrypted/decrypted through
  `app/security/encryption.py` (`encrypt_value` / `decrypt_value`).
  The key is loaded from `.env` (`ENCRYPTION_KEY`), never stored in the
  DB, never committed. Database models should call these two functions
  in field setters/getters rather than touching Fernet directly.
  `ENCRYPTION_KEY` must stay in Fernet format — 32 url-safe
  base64-encoded bytes — not a SHA-256/hex string; `Fernet()` rejects
  anything else at startup (verified directly against the library).
- **Database: SQLite via SQLAlchemy (async, `aiosqlite`) for now.**
  Chosen to match the "100% local" requirement with zero extra
  infrastructure; `DATABASE_URL` in `.env` is the only thing that would
  change to move to Postgres later.
- **LLM gateway reachability**: from inside the Linux container, the
  Mac host's native `llama-server` (port 8080, Metal-accelerated) is
  reached via `host.docker.internal:8080`, not `localhost`. In
  production on a VPS, the same `LLAMA_SERVER_URL` setting instead
  points at an Ollama/vLLM container on the internal Docker network.
- **Per-user isolation**: LangGraph's native checkpointer, keyed by a
  `thread_id` of the form `telegram_{user_id}`, `email_{email_hash}`
  (hash, not raw address), `matrix_{user_id}`.

## Security notes

- `/Users/mac/Documents/Code/Hermes/macos-arm64/.env` contains a live
  `API_SERVER_KEY` and a dashboard basic-auth password
  (`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=test`). **Neither was copied**
  into ChannelAgent's `.env` — both are internal secrets scoped to the
  vendored `hermes-agent` binary/dashboard, not credentials meant for a
  different application. ChannelAgent's `API_SERVER_KEY` was generated
  fresh instead (a random 32-byte hex token — same shape as Hermes's
  key by coincidence of length, not an actual SHA-256 digest of
  anything, and there is no format requirement on it yet since the
  admin API itself isn't implemented).
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` *were* reused
  as-is in ChannelAgent's `.env` — same physical bot and operator, no
  reason to rotate. `TELEGRAM_ALLOWED_USERS` will only ever be used to
  seed the initial DB-backed user row, never read directly for
  authorization decisions once the DB/API auth layer exists.

## Current state / what exists so far

- Git repo initialized, `.gitignore` protects `.env`, `*.db`, key
  material.
- `.env.example` documents all expected settings (no real secrets).
- `.env` (real, git-ignored, never commit): freshly generated
  `ENCRYPTION_KEY` and `API_SERVER_KEY` (not reused from Hermes — see
  Security notes above), plus `TELEGRAM_BOT_TOKEN` /
  `TELEGRAM_ALLOWED_USERS` reused as-is from
  `Hermes/macos-arm64/.env` (same bot/operator). Email and Matrix
  fields left empty, same as in Hermes.
- `start.sh`: adapted from Hermes's own start.sh. No per-platform
  dispatch (ChannelAgent targets one Linux container everywhere);
  instead validates `.env`/`ENCRYPTION_KEY`, sets up a local venv +
  `requirements.txt`, and on macOS checks that `llama-server` answers
  on `localhost:8080`. Will switch to building/running the Docker
  container once `app/main.py` and the Dockerfile exist.
- `app/config.py`: pydantic-settings loader, fails fast if
  `ENCRYPTION_KEY` is missing.
- `app/security/encryption.py`: Fernet encrypt/decrypt helpers.
- `docs/ARCHITECTURE.md`: full target architecture, Mermaid diagram,
  Hermes audit findings.
- `requirements.txt`: langgraph, fastapi, sqlalchemy+aiosqlite,
  cryptography, python-telegram-bot, matrix-nio, etc.

## Backlog (2026-09-18)

The full remaining build is tracked as 32 GitHub issues on
`ka8t/ChannelAgent` (private repo), not in this file: 7 epics (#1-#7,
one per architecture phase) plus 25 implementation issues linked from
them. Labels mirror the priority scheme from `ka8t/AuditRust`
(`P0-critical`/`P1-high`/`P2-medium`/`P3-low`) plus `area:*` component
labels. Start from the epics for the current picture; don't re-derive
the plan here — `gh issue list --repo ka8t/ChannelAgent` is the source
of truth for what's done vs. outstanding, this file is not.

## P0 milestone: done (2026-09-18)

All 8 `P0-critical` issues (#8, #9, #10, #12, #15, #16, #18, #19) are
implemented and closed, each verified with a real run (SQLite file,
mock LLM backend, `docker build`/`docker run`), not just written —
see each issue's closing comment for what was actually tested and any
bugs the verification caught. New files:

- `app/db/models.py` — `User` / `ChannelIdentity` / `Permission`.
  `ChannelIdentity.external_id` is the plaintext lookup key (a hashed
  email for the email channel, via `app.security.hashing`); only
  `raw_address` (email) is stored encrypted, since Fernet output can't
  be queried by equality.
- `app/db/types.py` — `EncryptedString`, a SQLAlchemy `TypeDecorator`
  so encryption happens transparently at the ORM boundary.
- `app/db/session.py` — async engine/session/`init_db()`.
- `app/security/hashing.py` — `channel_identifier_key()`, shared by
  the Auth Node and `app/graph.py` so the DB lookup key and the
  LangGraph `thread_id` can never drift apart for the same identity.
- `app/security/auth.py` — `authorize()`, fail-closed.
- `app/graph.py` — the LangGraph orchestrator. Uses
  `Annotated[list[BaseMessage], add_messages]` as the state's
  `messages` field — **not optional**: without that reducer, every new
  turn replaces the checkpointed history instead of appending to it,
  silently erasing prior conversation. `MemorySaver` is in-process
  only (no restart-durability yet — acceptable per the epic's own
  scope note, revisit if that assumption changes).
- `Dockerfile` (`python:3.12-slim`, not the newest interpreter, so
  every dependency has a prebuilt wheel), `.dockerignore`,
  `docker-compose.yml`, `app/main.py` (minimal entrypoint — no channel
  adapters wired in yet, that's epic #6).
- `requirements.txt` gained `greenlet` (SQLAlchemy's async engine needs
  it explicitly; not always pulled in transitively) — found by a real
  `MissingGreenlet` failure during verification, not by inspection.

`host.docker.internal:8080` reachability from inside a container was
verified against a mock server (documented on #20, left open — that
still needs a real `llama-server` to close properly).

Next up: the `P1-high` issues (#13, #14, #17, #22-24, #26-27).

## #20 closed, and start.sh fixed (2026-09-18)

- **#20 closed for real**: started the actual native llama-server
  (Hermes's binary/model/flags), confirmed it directly, then ran
  `app.graph.run_turn()` — the real code path, not a curl — inside the
  actual container and got a real completion back over
  `host.docker.internal:8080`. Documented as a reproducible check in
  `README.md`'s Verify section.
- **start.sh now auto-starts llama-server** instead of just warning
  (using `LLAMA_SERVER_BIN`/`MODELS_DIR`/`MODEL_FILE`/`LLAMA_PORT`,
  new `.env` variables — shell-only, never read by the Python app;
  `app/config.py` gained `extra="ignore"` so unknown `.env` vars don't
  break `Settings()`), and takes `--native` to run the app directly via
  a local venv instead of Docker. **The two modes need different
  `LLAMA_SERVER_URL`s** (`host.docker.internal` only resolves inside a
  container) — `--native` overrides it to `localhost` explicitly,
  Docker mode leaves `.env`'s value alone. Untracked as its own issue
  before (#33, created and closed same-session with the fix).
- **Real bug found while verifying `--native`** (the first time the
  app ran outside Docker): `app/db/session.py`'s `init_db()` never
  created the parent directory for a relative SQLite path — invisible
  under Docker because the `Dockerfile`/`docker-compose.yml` happen to
  pre-create `data/`. Fixed with `_ensure_sqlite_dir_exists()` in that
  same file, not by having `start.sh` paper over it with an extra
  `mkdir`.

## Closed-issue audit (2026-09-18)

Per the "never close an issue unless actually implemented" rule above,
re-ran every closed issue's verification fresh, from a clean state,
rather than trusting the original closing comments:

- #8, #9, #10, #12 (DB models, `EncryptedString`, session, Auth Node):
  re-ran the full DB+encryption+auth script — round-trip, fail-closed
  denial, immediate revocation all still hold.
- #15, #16 (LangGraph skeleton, checkpointer): re-ran the mock-backend
  isolation test — independent per-user threads, correct history
  accumulation, hashed email `thread_id`, all still hold.
- #18, #19 (Dockerfile, docker-compose): fresh `docker build` +
  `docker run`, no `.env` still fails fast on `ENCRYPTION_KEY`, with
  `.env` still boots and creates the DB on the mounted volume.
- #20 (real `host.docker.internal` reachability): started the real
  native `llama-server` again and re-ran `app.graph.run_turn()` inside
  the real container — still returns a real completion.
- #33 (`start.sh` auto-start / mode split / dir-creation fix):
  re-confirmed `_ensure_sqlite_dir_exists()` creates a missing `data/`
  from scratch, and re-ran both `start.sh` modes against the
  already-running `llama-server` — native still overrides
  `LLAMA_SERVER_URL` to `localhost`, default (Docker) mode still keeps
  it at `host.docker.internal`.

Result: all 10 closed issues held up. Nothing reopened. All test
containers/images/processes/data removed afterward — this audit left
nothing running.

## P1 progress: #13, #14, #26, #17, #27 closed (2026-09-18)

- **#13/#14**: the DB/auth schema from #8/#12 already supported
  per-channel role scoping (`Permission` keys off `ChannelIdentity`,
  not `User`) — documented in `docs/ARCHITECTURE.md`, verified the
  same `User` can be admin on Telegram and merely a chat user on Email.
  `app/db/bootstrap.py::bootstrap_admin_from_env()` seeds the first
  admin from `TELEGRAM_ALLOWED_USERS` on an empty DB, verified
  idempotent (a second boot doesn't duplicate it) and that
  `TELEGRAM_ALLOWED_USERS` is genuinely never read again afterward.
- **#26/#17**: `app/channels/schema.py::NormalizedEvent` carries a
  `reply()` callback so `app/channels/dispatch.py::dispatch_event()`
  can deliver a response without knowing which channel it came from —
  the shared Auth-then-graph-then-reply pipeline every adapter calls.
- **#27 (Telegram adapter)**: the first channel actually wired end to
  end. **A real live test with the user**, not just code — started the
  real app (real bootstrap admin, real Telegram long-polling, real
  native `llama-server`), asked the user to message the real bot,
  confirmed server-side (`getUpdates` → real LLM call → `sendMessage`,
  all 200 OK) and by the user explicitly confirming they received the
  reply on their own device.
- **Operational finding, resolved same-session**: a local Hermes
  gateway process (`hermes_cli.main gateway run`, port 8645) was still
  polling the same `TELEGRAM_BOT_TOKEN` during this test, causing
  intermittent `Conflict: terminated by other getUpdates request`
  errors — Telegram allows only one long-polling connection per bot
  token. **The user confirmed Hermes is no longer used**, so both its
  launchd services were disabled (not just killed, which
  `KeepAlive: true` on `ai.hermes.gateway.plist` would have
  auto-restarted):
  ```
  launchctl unload -w ~/Library/LaunchAgents/ai.hermes.gateway.plist
  launchctl unload -w ~/Library/LaunchAgents/com.hermes.silent-failure-watchdog.plist
  ```
  Confirmed both fully stopped (`launchctl list`, `lsof -i :8645`, `ps
  aux` all empty afterward) and won't restart at next login (`-w`
  persists the disable).

  **Update, same session**: the user then asked to delete the `.plist`
  files outright, not just leave them unloaded. Removed:
  ```
  rm ~/Library/LaunchAgents/ai.hermes.gateway.plist
  rm ~/Library/LaunchAgents/com.hermes.silent-failure-watchdog.plist
  ```
  Re-confirmed fully clean afterward (no files, no `launchctl` entries,
  no processes, port 8645 free). `ai.hermes.gateway.plist` had no
  source template in the Hermes repo (unlike the watchdog one,
  `macos-arm64/scripts/com.hermes.silent-failure-watchdog.plist.example`)
  — if Hermes's gateway is ever needed again, it would need
  regenerating via Hermes's own setup tooling (`hermes gateway setup`),
  not a file restore. The Hermes project directory itself
  (`/Users/mac/Documents/Code/Hermes`) was not touched — only the
  locally-installed launchd services. No further token-sharing conflict
  is expected going forward; if it recurs, something reinstalled these
  outside this change.

## Admin API done (2026-09-18): #22, #23, #24, #25 closed

`app/api/` — FastAPI, protected end-to-end by `API_SERVER_KEY` bearer
auth (`app/api/deps.py::verify_api_key`, attached via `dependencies=`
at the app level). Full CRUD for users and channel identities, and
grant/revoke for permissions (`app/api/routes.py`); `revoke_permission`
added to `app/security/auth.py` alongside the existing `grant_permission`.

- **`ChannelIdentityCreate` takes a raw identifier**, not a pre-computed
  `external_id` — the route hashes it via the same
  `app.security.hashing.channel_identifier_key()` the Auth Node uses,
  so an identity created through the API is immediately queryable by
  `authorize()`. Verified directly: granted a permission via HTTP,
  then called `authorize()` in the same process (bypassing the API) and
  confirmed it now allows that identity — and the reverse for revoke.
- **Real bug found and fixed while verifying #25**: FastAPI's
  automatic `/docs`/`/redoc`/`/openapi.json` routes are wired up
  outside ordinary path operations and are **not** covered by
  app-level `dependencies=` — they shipped completely unauthenticated
  the first time this was tested, silently defeating #22's whole
  point. Fixed by disabling the automatic ones (`docs_url=None` etc.)
  and re-implementing both as ordinary routes in `app/api/app.py`,
  which the dependency does cover. This is exactly the kind of gap the
  "never close unless verified" rule exists to catch — the first pass
  only tested `/users`, not FastAPI's own bolted-on routes.
- Wired into `app/main.py` (a `uvicorn.Server` task alongside the
  Telegram adapter), gated on `API_SERVER_KEY` being set.
  `docker-compose.yml` now publishes `API_SERVER_PORT`. Verified for
  real: built the actual image, ran the actual container, hit it with
  `curl` from the host — 401 without the key, 200 with the real
  `API_SERVER_KEY` from `.env`, returning the real bootstrap admin
  (id 7231548225) created by #14 in the same running instance.
