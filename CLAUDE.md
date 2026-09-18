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

Next up: the `P1-high` issues (#13, #14, #17, #20, #22-24, #26-27).
