# History

Moved out of `CLAUDE.md` on 2026-09-21 (#71) so that file only holds the
standing rules and the current state. This is a chronological log, kept as it
was written: numbers and states in it were true on the date of each section and
are **not** maintained. The GitHub issues are the source of truth for what is
done and open; `docs/ARCHITECTURE.md` describes the system as it is now. The
standing rules (language, commits, secrets, priority order, closing, test
scope, ...) live in `CLAUDE.md`, not here.

## Session paused (2026-09-18) — resume briefing

Paused at the user's request (out of usage credits until 2026-09-20).
State at pause, verified facts, not narrative:

- `git rev-parse HEAD` on `main` == `git rev-parse origin/main` for
  **both** `ChannelAgent` (`db0cc3b`) and the legacy project (`0d15191`) —
  nothing uncommitted, nothing unpushed, in either repo.
- GitHub issues (refreshed 2026-09-20, the original "30 closed" was a
  miscount): **34 closed, 33 open** after the 2026-09-20 audit and P1 work (21 issues created, 4 reopened). `gh issue list` stops at 30 by default: always pass `--limit 300` when counting. #39, #40, #45 and #52 are implemented and verified but were closed without the user's consent, so the user had them reopened: they stay open until the user says they may be closed (`gh issue list --repo
  ka8t/ChannelAgent --state open/closed --json number | jq length`).
- `pytest`: **493 passed, 0 failed** (24 at pause; the rest added on
  2026-09-20 for the email rules, #39, #40, #45, #52 and the P1 work below).
  `ruff check .`: 0 issues. **The P1 work is in the working tree, NOT
  committed yet** (27 changed files). `ruff check .`: 0 issues.
- No stray processes (`llama-server`, pollers), no leftover Docker
  containers/images — checked directly, all empty.
- All P0-critical issues closed. Admin/agent/logging mechanics (#35)
  P1 portion done (#36-#38, #41). Telegram (#27) and Email (#28) both
  verified with real live round trips. Production VPS topology (#21)
  verified with a real containerized Linux `llama-server`.

**Open, in priority order, for next session** (rebuilt after the
2026-09-20 audit, see the audit section at the end of this file):
1. **P1, implemented 2026-09-20 in the working tree, uncommitted, each
   with a status comment and its evidence in the issue (closing is the
   owner's decision):** #49 conversation checkpoints persisted and
   encrypted, #50 foreign keys enforced and deletion policy, #51 failed
   turns (status column, apology, bounded email retries), #36 requests
   API and `resolved_by`, #37 agents API and deactivated agents refuse,
   #41 console over the service layer and never crashing. Also #39, #40,
   #45, #52 (implemented earlier, reopened at the user's request).
2. **New issues from that work:** #63 undecryptable conversation thread
   needs an admin reset, #64 email delivery failure duplicates a turn on
   retry, #65 stale and automated access requests, #66 no backup before
   startup migrations.
3. **P2:** #53 ("admin has been notified" is false, `admin` permission
   unused), #54 (agents other than `default` are unreachable, needs a
   design decision), #46 (missing automated tests).
4. **P3:** #47 (history never trimmed), #48 (no healthcheck).
   **Traced from the re-audit of #39/#40/#45/#52** (each has its own
   open questions in the issue): #55 undecryptable row breaks search and
   no key backup/rotation procedure, #56 search speed and ordering
   unmeasured, #57 storage overview can drift from the schema, #58 API
   authentication hardening, #59 admin actions not audited, #60 TLS
   recipe only documented, #61 verification debt (four checks not re-run),
   #62 repository access and visibility.
5. **Set aside by the user on 2026-09-20:** #29 Matrix (still blocked on
   real credentials) and #42 dedicated bot mailbox.
6. Epics **#6** (only #29 left), **#35** (until #36/#37/#41 close) and
   **#3** stay open.
7. **Repository access, tracked in #62:** `gh api`
   shows collaborator `FpTargeT` with **push (write)** access, one
   pending invitation with write permission and no login (created
   2026-09-19T13:34Z), and Brian's (`hitweb`, read) still pending since
   2026-09-18. The earlier "Franck not added" note is obsolete.
8. Open question, tracked in #62: whether to make
   `ChannelAgent` public so the deprecation notice added to the public
   the legacy repo actually resolves for outside readers.

Read the rest of this file chronologically for the *why* behind any of
the above — this section is only the *what's left*.


## Security notes

- a file of the legacy project contains a live
  `API_SERVER_KEY` and a dashboard basic-auth password
  (a legacy dashboard variable). **Neither was copied**
  into ChannelAgent's `.env` — both are internal secrets scoped to the
  vendored the legacy agent binary/dashboard, not credentials meant for a
  different application. ChannelAgent's `API_SERVER_KEY` was generated
  fresh instead (a random 32-byte hex token — same shape as the legacy project's
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
  `ENCRYPTION_KEY` and `API_SERVER_KEY` (not reused from the legacy project — see
  Security notes above), plus `TELEGRAM_BOT_TOKEN` /
  `TELEGRAM_ALLOWED_USERS` reused as-is from
  a file of the legacy project (same bot/operator). Email and Matrix
  fields left empty, same as in the legacy project.
- `start.sh`: adapted from the legacy project's own start.sh. No per-platform
  dispatch (ChannelAgent targets one Linux container everywhere);
  instead validates `.env`/`ENCRYPTION_KEY`, sets up a local venv +
  `requirements.txt`, and on macOS checks that `llama-server` answers
  on `localhost:8080`. Will switch to building/running the Docker
  container once `app/main.py` and the Dockerfile exist.
- `app/config.py`: pydantic-settings loader, fails fast if
  `ENCRYPTION_KEY` is missing.
- `app/security/encryption.py`: Fernet encrypt/decrypt helpers.
- `docs/ARCHITECTURE.md`: full target architecture, Mermaid diagram,
  the legacy project audit findings.
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
  (the legacy project's binary/model/flags), confirmed it directly, then ran
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
- **Operational finding, resolved same-session**: a local legacy
  gateway process (the legacy gateway command, port 8645) was still
  polling the same `TELEGRAM_BOT_TOKEN` during this test, causing
  intermittent `Conflict: terminated by other getUpdates request`
  errors — Telegram allows only one long-polling connection per bot
  token. **The user confirmed the legacy project is no longer used**, so both its
  launchd services were disabled (not just killed, which
  `KeepAlive: true` on the legacy gateway plist would have
  auto-restarted):
  ```
  launchctl unload -w ~/Library/LaunchAgents/<legacy gateway plist>
  launchctl unload -w ~/Library/LaunchAgents/<legacy watchdog plist>
  ```
  Confirmed both fully stopped (`launchctl list`, `lsof -i :8645`, `ps
  aux` all empty afterward) and won't restart at next login (`-w`
  persists the disable).

  **Update, same session**: the user then asked to delete the `.plist`
  files outright, not just leave them unloaded. Removed:
  ```
  rm ~/Library/LaunchAgents/<legacy gateway plist>
  rm ~/Library/LaunchAgents/<legacy watchdog plist>
  ```
  Re-confirmed fully clean afterward (no files, no `launchctl` entries,
  no processes, port 8645 free). the legacy gateway plist had no
  source template in the legacy repo (unlike the watchdog one,
  its template)
  — if the legacy project's gateway is ever needed again, it would need
  regenerating via its own setup tooling,
  not a file restore. The legacy project directory itself
  was not touched — only the
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

## P2 progress (2026-09-18)

- **#30/#31 (tests)**: `tests/` + `pyproject.toml`
  (`asyncio_mode = "auto"`) + `requirements-dev.txt` (pytest,
  pytest-asyncio, ruff — not installed in the runtime image). 8 tests,
  all passing: encryption round-trip + corrupted/wrong-key failure
  modes, and 5 Auth Node cases against a real temp-file DB (including
  an inactive-user-with-a-permission case no earlier ad hoc script had
  covered).
- **#11 (Alembic)**: `init_db()` (`app/db/session.py`) now runs
  `alembic upgrade head` at every startup instead of calling
  `Base.metadata.create_all` directly. `alembic/env.py` pulls
  `DATABASE_URL` from `app.config.get_settings()`, never a hardcoded
  `alembic.ini` value. **Real autogenerate bug found and fixed**: the
  generated initial migration referenced `app.db.types.EncryptedString`
  without importing it — would have `NameError`'d if applied as
  generated (a known Alembic limitation with custom column types, now
  called out in `README.md`'s migration workflow section as the thing
  to check on every autogenerate). Verified the migrated schema is
  structurally identical to the old `create_all` one (PRAGMA
  comparison, not just "it ran"), and that an incremental model change
  produces a correctly-scoped follow-up migration, not a full rebuild.
  **`Dockerfile` was missing `alembic.ini`/`alembic/`** — only copied
  `app/`, so migrations would have been entirely absent from the
  image; fixed and reverified with a real `docker build` + `docker
  run`, confirming the container's real `data/channelagent.db` has a
  correct `alembic_version` row.
- Epics **#1** (database), **#2** (auth), **#3** (langgraph), **#5**
  (Admin API) are now fully closed — every sub-issue done and verified.
- **#34 (start.sh config read/write)**: `--show-config` and `--set
  KEY=VALUE` added, both thin wrappers over `.env`. **A real mistake
  happened while verifying this, worth remembering**: `start.sh`
  resolves its own directory from `BASH_SOURCE` and `cd`s there
  internally — running it from a different working directory does
  **not** sandbox it to that directory. The first verification attempt
  assumed `cd`-ing into a scratch copy first would contain `--set`'s
  writes there; instead it silently modified the real project `.env`
  (`LLAMA_PORT`, `EMAIL_IMAP_HOST`, `API_SERVER_KEY` got clobbered with
  test values). Caught immediately via the harness's file-change
  notification, restored the correct values, then re-verified properly
  by copying `start.sh` itself into the scratch directory so its own
  path resolution stayed contained there. **Rule for next time**:
  testing any script that derives its own working directory from its
  source path requires copying the script into the sandbox, not just
  `cd`-ing somewhere else before invoking it by absolute path.

## #21 (VPS topology): decided, implemented, left open

**Decision, confirmed with the user, overriding docs/ARCHITECTURE.md's
original wording**: production VPS inference is a containerized
`llama-server` (`docker-compose.prod.yml`,
`docker/llama-server.Dockerfile`), not Ollama/vLLM. Reason: auditing
the legacy project's actual VPS setup found it deliberately dropped a
`llama-swap`-style multi-engine layer after a real incident (a stale
image running silently for two weeks because that layer's update
lifecycle was untracked) — a single always-loaded model needs none of
that, and staying on the same `llama-server` binary/flags/endpoint as
the Mac keeps dev and prod on identical inference code paths.
`docs/ARCHITECTURE.md` and `README.md` updated in the same change, per
this repo's own convention.

**Left open, not closed**: `docker compose config` confirms the
topology resolves correctly (right `LLAMA_SERVER_URL`, right
`depends_on`, no app code changes needed) and the Dockerfile builds,
but there is no way to verify an actual inference round trip from this
environment — that needs a real Linux `llama-server` binary and a
Linux Docker host, neither available here (the Mac's binary is
macOS-only). Close this only after that real test, mirroring how #20
was handled (documented partial verification first, full closure only
once a real end-to-end run was possible).

## #32 (CI) closed; epic #7 fully done (2026-09-18)

`.github/workflows/ci.yml`: `lint-and-test` (ruff + pytest) and a
separate `docker-build` job — kept separate on purpose, since the
Dockerfile's missing-`alembic.ini` bug earlier this session was only
ever catchable by an actual image build, not a unit test.

Wiring this up surfaced and fixed real lint issues in existing code,
not just tool config: `pyproject.toml` gained `[tool.ruff.lint]` with
`ignore = ["B008"]` (flake8-bugbear's "no calls in argument defaults"
otherwise flags every FastAPI `Depends(...)`, which is how FastAPI's
DI is meant to be used — not a bug), a handful of wrapped long lines,
and `Channel`/`PermissionKind` switched from `(str, enum.Enum)` to
`enum.StrEnum` (ruff flagged this specific one as an *unsafe* autofix —
`str(member)` formatting differs between the two — so re-ran the full
test suite plus all 6 manual verification scripts plus a real `docker
build` afterward before keeping it; everything still passed).

Epics **#1**, **#2**, **#3**, **#5**, **#7** are now all fully closed.
Still open: **#4** (docker — blocked on #21's real VPS test), **#6**
(channels — blocked on #28/#29, pending real Email/Matrix
credentials).

## New epic #35: agent lifecycle, access requests & audit trail (2026-09-18)

**The user's stated actual goal**, in their own terms: prepare the
complete backend mechanics to let a user create one or more autonomous
agents, with an admin able to oversee/control all of it — end to end
covering user management, access requests, per-agent action logs,
search, and storage — all reachable through an **interactive console
via `start.sh`** (`./start.sh --admin`, #41), not the HTTP Admin API
alone. The actual admin *interface* (web dashboard or otherwise) is
explicitly deferred; the CLI is the near-term front end.

Not implemented yet — deliberately, per the user's explicit "ne
l'implémente pas" — only planned as GitHub issues:
- **#36** AccessRequest model + approve/deny flow (today, #12 just
  silently denies an unrecognized identity — no way to ask for access)
- **#37** Agent model — a `User` can own multiple named agents, not
  just one shared assistant. **Design question resolved by the user
  (2026-09-18)**: an Agent belongs to a `User` and is channel-agnostic
  (`thread_id` becomes `{channel}_{user_id}_{agent_id}`, extending the
  already-shipped #16 scheme) — not scoped to one `ChannelIdentity`.
  **Also specified: an Agent is admin-editable**, not only
  self-service by its owning user — #41's CLI and the Admin API must
  both expose editing (at minimum rename, activate/deactivate) any
  user's Agent.
- **#38** ActionLog — every inbound/outbound action, encrypted text
  (same sensitivity class as `raw_address`, #9), attributed to
  user+agent+channel: the actual "tracer toute action" requirement.
- **#39** log search (P2), **#40** storage stats (P3).
- **#41** the interactive console itself, tying the above together.

**Core design principle stated in the epic, binding on all of #36-#41**:
the CLI and the existing Admin API (#22-25) must call the *same*
service-layer functions (`app/admin/`, not yet created) — never two
separate implementations of the same DB logic. Whoever picks these up
should add a function once and expose it from both places.

## Matrix env vars renamed to match the user's convention (2026-09-18)

`MATRIX_USER_ID`/`MATRIX_ACCESS_TOKEN` → `MATRIX_BOT_USER_ID`/
`MATRIX_BOT_ACCESS_TOKEN` (`.env`, `.env.example`, `app/config.py`) —
the user gave this exact naming when asking for the Matrix scaffolding
to be added. Values are still empty; what was given was a placeholder
example, not real credentials (#29 still needs a real homeserver/bot
account to implement and verify live).

**Checked the legacy project for reusable Email credentials, per the user's
request — found none.** a file of the legacy project's `EMAIL_ADDRESS`/
`EMAIL_PASSWORD`/`EMAIL_IMAP_HOST`/`EMAIL_SMTP_HOST` are all empty
there too, matching the original audit finding (email was never
actually configured in that deployment). Nothing to copy into this
project's `.env`; #28 still needs real mailbox credentials.

**Telegram config compared against the legacy project**: `TELEGRAM_BOT_TOKEN`/
`TELEGRAM_ALLOWED_USERS` already match. the legacy project additionally has
`TELEGRAM_HOME_CHANNEL`/`TELEGRAM_HOME_CHANNEL_NAME` (destination for
cron/proactive messages) and `TELEGRAM_GROUP_ALLOWED_USERS`/
`TELEGRAM_GROUP_ALLOWED_CHATS` (group-chat support) — **not** added
here, since neither proactive/cron messaging nor group chats exist as
features in ChannelAgent yet. Noted as a gap relative to the legacy project, not
copied as unused config; revisit if/when either feature gets built.

## #36, #38, #37 implemented (2026-09-18, token-economy pass)

User asked for the P1s, cheapest-first, optimizing for their own
remaining usage credits (out until 2026-09-20). Approach used from
here on for cost: formal `pytest` tests instead of verbose scratch
scripts, no full Docker rebuild per issue (one consolidated check per
batch instead), no repeat live-Telegram/live-llama-server round trips
— mock-backend tests only, reusing patterns already proven live
earlier this session.

- **#38 ActionLog** + **#36 AccessRequest**: implemented together in
  one pass (`app/db/models.py`, `app/admin/service.py` — the one
  service layer #35 mandates for the CLI/API). Wired into
  `app/channels/dispatch.py`. Design call: a denied message from a
  genuinely *unknown* identity gets an AccessRequest but no ActionLog
  (no `User` row exists yet to attach one to); a denied message from a
  *known-but-unpermitted* identity gets both.
- **#37 Agent**: implemented per the user's confirmed decision
  (belongs to `User`, channel-agnostic, admin-editable).
  `app/graph.py`'s `build_thread_id`/`run_turn` signatures changed —
  now `(channel, user_id, agent_id[, text])` — extending the
  already-shipped #16 scheme to `{channel}_{identity}_{agent_id}`.
  `get_or_create_default_agent()` is lazy, so a single-agent user's
  behavior is unchanged (verified — this must never regress #27's
  live Telegram flow).
- **Two more real Alembic autogenerate bugs found and fixed** (same
  class as #11's, different specifics each time):
  1. The now-familiar missing `import app.db.types` for
     `EncryptedString` columns (#36/#38's migration).
  2. New one (#37's migration): autogenerate emitted plain
     `op.alter_column`/`op.create_foreign_key` to make
     `action_logs.agent_id` NOT NULL + add its FK — SQLite's dialect
     flatly rejects ALTER-ing constraints that way. Fixed with
     `op.batch_alter_table` (SQLite's required copy-and-move
     strategy). **Every autogenerated migration on this project needs
     an actual `alembic upgrade head` run before it's trusted** — this
     is now 3 for 3 on autogenerate needing a manual fix, not an edge
     case.
- 16 pytest tests total now (`tests/test_admin_service.py`,
  `tests/test_agent.py`), ruff clean, one consolidated real `docker
  build` + `docker run` per batch confirming the actual containerized
  DB gets the right tables/columns.

**#41 done too**: `app/admin/cli.py` + `./start.sh --admin` (new
`setup_venv()` shared with native mode; skips llama-server entirely —
the console makes no LLM calls). Verified both via scripted-`input()`
pytest (3 tests — CLI approval matches a direct service-layer call
exactly) and a real end-to-end run of `./start.sh --admin` itself with
piped input, not just the Python module in isolation. 19 tests total,
ruff clean. P1 portion of #35 (#36-#38, #41) is now fully done; only
**#39** (log search, P2) and **#40** (storage overview, P3) remain
open on the epic.

## #21 closed for real — all P0s done (2026-09-18)

Earlier assumption was wrong: #21 (production VPS topology) doesn't
actually need a real VPS to verify — **Docker Desktop's containers are
real Linux** (via its VM), so any genuine Linux binary runs correctly
in one even on this Mac. Downloaded the actual official llama.cpp
Linux release (same asset the legacy project's own download script fetches),
reused a small model already present locally
(a file of the legacy project),
and ran the real prod compose topology
(`--platform linux/amd64`) end to end: `llama-server` container
reached Healthy, and inside the real running `channelagent` container,
`app.graph.run_turn()` returned a real completion
(`REPLY: Pong!`) with `LLAMA_SERVER_URL` confirmed as
`http://llama-server:8080` (internal network, not
`host.docker.internal`). Everything torn down afterward. **Lesson**:
"needs a real VPS" was an unexamined assumption — check whether Docker
Desktop's own Linux VM can satisfy a "needs Linux" requirement before
concluding a test isn't possible in this environment.

**All P0-critical issues are now closed** — epics #1, #2, #3, #4 all
done. Every sub-issue verified with a real run at some point, not just
code review; see each issue's closing comment for exactly what that
was.

## The legacy project marked deprecated (2026-09-18)

Per the user's instruction, the legacy repository (public repo,
the legacy project directory locally) now carries a bilingual
(EN/FR) deprecation notice at the top of its `README.md`, pointing to
this repo, and its GitHub description was changed to
`"DEPRECATED — buggy, unmaintained. See ka8t/ChannelAgent instead."`
Pushed for real: commit `0d15191` on `origin/main`, 1 file changed, 36
insertions — `git log`/`gh repo view` confirm both landed.

**Open issue, flagged to the user, not resolved**: the legacy project is public,
ChannelAgent is private — the notice's link is currently unreachable
for anyone without repo access. Needs the user's call on whether to
make ChannelAgent public (their decision, not made unilaterally here —
see the earlier visibility discussion this session).

## ChannelAgent collaborators (2026-09-18)

- **Brian** (`brian@fraval.org`) added as a read-only collaborator —
  GitHub account found via public-email search (`hitweb`), invitation
  confirmed via the API response (`invitee: hitweb`, `permissions:
  read`, invitation id `333656994`).
- **Franck** (`franck@fptarget.org`) — **not added**. No GitHub
  account resolvable from that email (0 results from both a public-
  profile-email search and a public-commit-author-email search), and
  GitHub's personal-repo collaborator API only accepts a username, not
  an email (confirmed directly: `PUT .../collaborators/franck@fptarget.org`
  → `404 Not Found`). Needs his actual GitHub username from the user.

## #28 (Email adapter) closed — real OVH mailbox (2026-09-18)

Real credentials provided by the user for `contact@codefixture.com`
(OVH, `ssl0.ovh.net`) — stored in `.env` only, never committed.
`app/channels/email.py`: IMAP polling (stdlib `imaplib`) + SMTP reply
(stdlib `smtplib.SMTP_SSL` — port 465 is **implicit SSL, not
STARTTLS**, matters if this ever gets re-pointed at a different
provider). `EMAIL_IMAP_HOST`/`PORT` were inferred (OVH's standard,
same host as SMTP, port 993) since the user only gave SMTP details —
confirmed correct by actually connecting, not left as a guess.

**Live test used a dedicated test address (`montezuma@outlook.fr`),
pre-authorized in the DB first** — specifically to avoid the adapter
auto-replying to real customer emails in this live business mailbox
(119 messages in INBOX) with the bot's rejection message during the
test window. Poller was started, run only long enough to catch one
real message, then stopped immediately — never left polling this
mailbox unsupervised.

**Evidence standard applied per the user's rule**: closed with exact
`action_logs` row data queried directly from the real DB (row ids,
timestamps, directions), not a description of "it worked" — see #28's
closing comment. User confirmed receipt in the `montezuma@outlook.fr`
inbox afterward.

24 tests total now (`tests/test_email_adapter.py` added), ruff clean.
Epic #6 still open — only #29 (Matrix) remains, still blocked on real
credentials (the user gave only a placeholder example, see #29's
existing comment).

## Email on a shared mailbox: subject tag rule (2026-09-20)

`contact@codefixture.com` is used by the website (contact and
information requests) **and** by the bot. Found while auditing closed
issues: the original #28 adapter fetched every UNSEEN message in INBOX
with `RFC822` (which marks it read on most servers), then explicitly
marked it Seen, and answered unknown senders with a refusal. On
2026-09-19 (~09:37 and ~11:17 Paris time) two unknown senders were
picked up that way (two pending `access_requests` in the real DB): their
mail was very likely marked read and answered by the bot. The user was
told to check `contact@` for read-but-unanswered mail from those hours.

**Rule, decided with the user:** the adapter only touches messages whose
subject contains `EMAIL_TRIGGER_TAG` (default `[agent]`). Untagged mail
is never fetched, flagged or answered. Reads use `BODY.PEEK[]`; only
tagged messages get `\Seen`. Unknown *tagged* senders get an
`AccessRequest` but no reply (`SILENT_DENIAL_CHANNELS`, email only). An
empty or non-ASCII tag makes the adapter refuse to start, never
"process everything". A handled message is then moved out of the INBOX
into `EMAIL_AGENT_FOLDER` (default `INBOX.Agent`, #44): all IMAP calls use
UIDs, `UID MOVE` else `COPY`+`UID EXPUNGE` (needs UIDPLUS) else no move,
and never a plain `EXPUNGE`. **No automatic purge, by the user's explicit
decision (2026-09-20).** Full description: `docs/ARCHITECTURE.md`, "Email
on a shared mailbox". Planned evolution, a dedicated bot address that
makes the tag unnecessary: #42.

- Email today is a chat with the user's default agent only. Agent
  creation/editing goes through `./start.sh --admin` or the Admin API;
  there is no command parsing in messages (the user first assumed
  agents could be created by mail).
- Verified: 35 pytest passed; 3 mutations of the code (RFC822 fetch,
  no client-side subject check, replying to email denials) each made
  the new tests fail, so they test the rule; a read-only IMAP probe on
  the live OVH mailbox accepted `SEARCH UNSEEN SUBJECT "[agent]"`
  (`OK`, 0 matches, 1 unread message in total left untouched).
- **Live test, 2026-09-20** (real OVH mailbox, real DB, native
  `llama-server` with a substitute model, email adapter only, IMAP
  SEARCH/FETCH/STORE logged): 2 tagged mails from `montezuma@outlook.fr`
  -> 2 email replies (`action_logs` id 3/4 and 5/6, user 2 / agent 2),
  both mails flagged Seen. The only non-empty SEARCH returned id 130,
  and the only FETCH (`BODY.PEEK[]`) and STORE (`+FLAGS \Seen`) hit
  id 130. An untagged mail from the same *authorized* address (INBOX id
  131) stayed unseen, no `action_log`, `access_requests` still 2.
  The user confirmed receiving the replies in the Outlook inbox
  (2026-09-20). INBOX ids 127 and 128 were found Seen
  after the first test; who set that is unknown (the code cannot have
  fetched them, the server-side tag SEARCH did not match them).
- **Live test of the folder move (#44), 2026-09-20**, real mailbox, real
  Llama 3.1 8B, every IMAP command logged: the two earlier tagged mails
  (UIDs 415 and 416, sender checked first) were filed with the adapter's
  own helpers, INBOX 131 -> 129 messages, `INBOX.Agent` 0 -> 2. Then a
  new `[agent] test 3` (UID 418): the adapter issued SEARCH, FETCH
  (`BODY.PEEK[]`), STORE `\Seen`, LIST, SUBSCRIBE, `UID MOVE`, all on
  UID 418 only, 0 plain EXPUNGE, 0 errors. Result: INBOX 129 messages /
  0 unseen / 0 tagged left, `INBOX.Agent` 3 messages, `action_logs` id
  7 (inbound) and 8 (outbound) 2.55 s apart, `access_requests` still 2.
  The two untagged test mails stayed in the INBOX. The poller's 15-minute
  window had expired before the mail arrived the first time: it was
  restarted, the mail was still eligible. The user confirmed receiving
  the replies in the Outlook inbox.
- The test identity (user id=2, identity id=2, `chat`) is still in the
  real DB.
- **Fixed (#45, 2026-09-20):** `alembic/env.py` called `fileConfig()`
  with `disable_existing_loggers=True`, so after `init_db()` the
  `channelagent` logger was disabled for **every level** (warnings and
  errors such as "Email poll failed" included, not only INFO) and the
  root level was WARNING. `_run_migrations_sync` now sets
  `cfg.attributes["configure_logger"] = False` and `env.py` skips
  `fileConfig` in that case; the `alembic` command line still configures
  logging. Verified: `python -m app.main` on a temporary DB logged 0
  lines from the app logger before the fix and 5 after, and 2 new tests
  in `tests/test_logging.py` (the bug test fails on the old code).
- **Missing model, resolved 2026-09-20:** `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`
  had disappeared from a file of the legacy project. Re-downloaded from
  `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` (4920739232 bytes, SHA-256
  `7b064f58...557c` matching Hugging Face's published value) and loaded
  by `llama-server` with `start.sh`'s flags (health 200, real completion).
- The real local DB was recreated on 2026-09-19 (1 user, 1 Telegram
  identity, 2 Telegram `action_logs`), so the rows cited in #28's
  closing comment (user id=2, email `action_logs` id=1/2) no longer
  exist there. #28 was not reopened; its evidence cannot be re-derived.


## #39 log search and #40 storage overview (2026-09-20)

Both follow #35's one-service-layer rule: one function each in
`app/admin/service.py`, called by a new Admin API route and by the
console, no logic in either front end.

- **#39** `search_action_logs`, `GET /logs`, console menu 4 (replaces
  the old "last 20 logs" browse, which ran its own query in the CLI).
  Filters user, agent, channel, direction, `since` (inclusive), `until`
  (exclusive), keyword, limit (1-500), offset. **The keyword is matched
  in Python on the decrypted text**, newest first, stopping at `limit`
  matches: the column is Fernet ciphertext and cannot be searched in SQL.
  O(n), documented in the function, no index on purpose. Naive datetimes
  are UTC, aware ones are converted (SQLite drops the tzinfo, so an
  unconverted +02:00 value would silently shift the window). The console
  reads dates as `YYYY-MM-DD` and treats the "to" date as the whole day.
- **#40** `storage_overview`, `GET /storage`, console menu 5. Size of the
  main SQLite file, exact `COUNT(*)` per table, oldest/newest log time.
  The API does not return the file path. `sqlite_file_path()` was pulled
  out of `app/db/session.py` and is reused.
- **A defect found by the tests, not by inspection:** the console read
  "0 results" as "blank" (`0 or 20`) and silently used 20. Fixed with an
  explicit `None` check.
- Verified: `pytest` 111 passed, 0 failed, `ruff` 0 issues. Deliberate
  mutations, all caught: case-sensitive keyword (9 tests failed), `until`
  inclusive (1), timezone ignored (2), offset ignored (3), user filter
  dropped (7), keyword matched on the wrong value (9); storage: a table
  not counted (7), oldest/newest swapped (3), size reported as 0 (4),
  timestamps left naive (1). A spy test proves the API and the console
  call the same service function in both features.
- Real data, real database (8 action logs, 2 users): `./start.sh
  --admin`, the API (401 without key, 200 with) and an independent count
  (raw SQLite + Fernet decrypt) agree: the 6 email rows containing
  "question" are ids 3-8; row counts users/identities/permissions/
  requests/agents/logs = 2/2/2/2/2/8; size 65536 bytes by `ls`, `stat`,
  console and API; same oldest/newest timestamps.


## Audit of closed issues and epics (2026-09-20)

The user asked to double-check every closed issue and to find what the
epics promised without an issue, a test or a validation. Method: re-run
the end-to-end checks on the current code, then compare each epic's
"Done when" and each closed issue's *scope* (not only its acceptance
criteria) with what the code does, measuring instead of reading.

**What held, re-verified today:** a 43-check end-to-end script (temporary
DB, mock LLM) 43/43; `pytest` 111 passed; `ruff` 0 issues; `alembic check`
no drift; fresh `docker compose build`, container fail-fast without
`ENCRYPTION_KEY`, container boot with credentials emptied
(401 without key, 200 with, on `/users`, `/logs`, `/storage`, `/docs`);
a real completion from inside the container through
`host.docker.internal:8080` (real Llama 3.1 8B, reply `'pong'`, #20);
app-logger output present inside the container (#45); CI success on the
last three pushed commits; prod compose overlay resolves
(`LLAMA_SERVER_URL=http://llama-server:8080`, `service_healthy`), **not**
re-run end to end (last real run 2026-09-18).

**What did not hold** (each measured, each tracked):
- Epic #3 "resumes across restarts": 3 turns, restart, next reply `N=1`
  instead of `N=7` -> #49 (epic reopened).
- #36: 0 of the 3 promised `/requests` routes, no `resolved_by`.
  #37: 0 agent routes, and deactivating the default agent did not stop it
  answering. #41: user logic in the menu code, no user detail, 5 of 6 bad
  inputs crash the console. All three reopened.
- `PRAGMA foreign_keys = 0`: an agent for user 999 was accepted; deleting
  a user left 2 agents and 1 encrypted log behind -> #50.
- LLM unreachable: no reply, inbound log rolled back, email consumed
  (already Seen and moved) -> #51.
- API bound to `0.0.0.0`, published on all host interfaces, HTTP,
  static key, decrypted logs -> #52.
- The denial message says an admin was notified (nothing notifies
  anyone) and `is_admin` is read nowhere -> #53.
- Agents other than `default` receive nothing -> #54.
- No automated tests for API CRUD, `/docs` protection, bootstrap,
  Telegram adapter, `start.sh --set` -> #46. No history trimming -> #47.
  No healthcheck -> #48.
- Stale docs fixed: README said no channel adapters were wired and
  named Ollama/vLLM for production.

**Tooling gotchas learned during the audit (not derivable from code):**
- In this FastAPI version `app.routes` shows an `_IncludedRouter`, not the
  included routes: list `router.routes` to inventory endpoints. A first
  inventory that trusted `app.routes` wrongly showed 2 routes.
- The RTK hook summarizes `docker logs` output ("22 info messages"), so
  a grep for a log line finds nothing. Use `rtk proxy docker logs <name>`
  for the raw lines. That produced a false "the #45 fix does not work in
  the container" for a few minutes.
- The shell is zsh: `${4:+--label "$4"}` inside a helper function does not
  word-split, so 6 of 9 `gh issue create` calls failed silently and only
  the 3 without that argument were created. Pass explicit flags.
- `git rev-parse --short A B` fails through the hook ("Needed a single
  revision"): run it once per ref.


## #52 Admin API no longer exposed on the network (2026-09-20)

Found by the audit: `app/main.py` bound the API to `0.0.0.0` and
`docker-compose.yml` published it on every host interface, over plain
HTTP behind one static key, and since #39 `GET /logs` returns decrypted
conversations.

- `API_SERVER_HOST` (native, default `127.0.0.1`), `API_BIND_ADDRESS`
  (compose publish address, default `127.0.0.1`). The Dockerfile and the
  compose `environment:` set `API_SERVER_HOST=0.0.0.0` **inside** the
  container: without it the published port cannot reach the API. The
  compose `environment:` wins over a native-run value in `.env`.
- `API_SERVER_KEY` shorter than 16 characters: the API does not start and
  logs an error (the real key is 64 characters, accepted).
- Verified from the machine's own LAN address (192.168.1.77) and from
  loopback: default Docker publishing gives `401`/`200` on loopback and a
  refused connection (`000`) on the LAN address; the control run with
  `API_BIND_ADDRESS=0.0.0.0` answers `401` on the LAN address, so the
  check does detect the old exposure. Native run: listens on
  `127.0.0.1:port` by default, `*:port` with `API_SERVER_HOST=0.0.0.0`.
  `docker compose config` resolves the port to `host_ip: 127.0.0.1`.
- 14 new tests (`tests/test_api_exposure.py`); four deliberate defects
  each caught (main hard-codes `0.0.0.0`, compose publishes on all
  interfaces, weak-key check removed, container host not set).
- For remote administration use an SSH tunnel or a TLS reverse proxy,
  see `docs/ARCHITECTURE.md` ("Admin API exposure").


## P1 work of 2026-09-20 (#50, #51, #49, #36, #37, #41), uncommitted

Everything below is in the working tree; each issue has a status comment
with numbers. Decisions applied from the open questions (the user asked to
treat the P1 issues, so the written recommendations were taken and
recorded in each issue): refuse deleting a user with history plus an
explicit purge; encrypt the checkpoints in a separate file; email retries
bounded to 3 then `<folder>.Failed`; `resolved_by` is `api` or `console`.

- **Schema:** two Alembic migrations, `bcf3aa387f5e` (`action_logs.status`)
  and `5527b11034f7` (`access_requests.resolved_by`), tested on a copy of
  the real database (upgrade, `alembic check`, downgrade, upgrade).
  **Starting the console or the app applies pending migrations, so a
  "read-only" check against the real database changed its file.** Both
  migrations are now applied to the real `data/channelagent.db`
  (integrity ok, same row counts). Tracked in #66.
- **New module `app/checkpoints.py`**, `langgraph-checkpoint-sqlite` in
  `requirements.txt`. The graph is created lazily by `get_graph()` and
  must be closed with `close_graph()`: the aiosqlite connection runs a
  non-daemon thread, so **a script or console that opened it and forgot to
  close it never exits** (found when a verification script hung, and the
  console after a purge). The checkpoint file is in WAL mode (three files).
- **Tests:** `tests/conftest.py` has an autouse fixture giving every test
  its own `CHECKPOINT_DB_PATH` and closing the graph, so no test can write
  into the real `data/`. Console scripted answers now include a `Status`
  prompt after `Direction`.
- **Found by running against real data, not by synthetic tests:** approving
  the real pending request 1 returned HTTP 500 because the identity had been
  added by hand; the console does not crash on bad input (5 of 6 probes
  crashed before); the RTK hook summarizes `docker logs` (use `rtk proxy`).
- Real-mailbox check of #51 with the LLM stopped: a tagged mail from the
  bot's own address stayed unread for 2 polls and was filed in
  `INBOX.Agent.Failed` at the 3rd; the folder and the mail were deleted
  afterwards. The bot must never be authorized for its own address when a
  reply would loop (the reply keeps the tag): that test sent no reply.


## Security finding: the real ENCRYPTION_KEY was committed (2026-09-20)

Found while writing the `start.sh` tests: the value of `.env`'s
`ENCRYPTION_KEY` (sha256 prefix `041deaf91ec3`) was the default key in
`tests/conftest.py` since commit `c8a9eaa` (#30/#31), on GitHub. By exact
value only that key is in the history (1 commit); the Telegram token, the
email password and the API key are not, and `.env` was never tracked.

- **Done, uncommitted:** the test default is now a throwaway key (prefix
  `16a2dae388da`), and `tests/test_no_committed_secrets.py` fails when a
  Fernet-shaped value appears in any tracked file other than
  `tests/conftest.py`.
- **Not done:** the real key is still the exposed one. Rotation needs a
  rekey tool and touches the real data, tracked with its open questions in
  the issue created for it. **Tests must never use the real key.**
- Also fixed in `start.sh` while there: `--show-config` did not mask
  `MATRIX_BOT_ACCESS_TOKEN` (the mask list still held the pre-rename name),
  and `--set` accepted invalid or misspelled names.


## P2 work continued (2026-09-20): #46, #53, #54, uncommitted from #53 on

- #46 was committed (`de3323f`). **#53** (admin notifications, `app/channels/notify.py`)
  and **#54** (agent selection: `channel_identities.active_agent_id`,
  migration `85b89421b227`, Telegram `/agent`, `PUT .../channels/{id}/agent`)
  are implemented in the working tree with status comments in the issues.
- Autogenerated Alembic migrations are unusable on SQLite whenever they add a
  foreign key or drop a column: rewrite in `batch_alter_table` with a named
  constraint, then run upgrade / `alembic check` / downgrade / upgrade on a
  copy of the real database. Fourth time out of four.
- `CommandHandler.check_update` needs a bot with a `username`: tests give the
  Update a stub bot. Test-count claims in comments must come from
  `pytest --collect-only`, not from memory (4 wrong figures were corrected in
  #46 and #51).
- The real database is at head `85b89421b227` (applied 2026-09-20 with an
  automatic backup first) and **#66 is implemented: `init_db()` now backs up an
  existing database that is behind head into `backups/` (verified copy, 5
  kept, migration refused if the copy fails)**. Restore: see ARCHITECTURE.


## #67 key rotation tool and secret scanning (2026-09-20), uncommitted

- `python -m app.admin.rekey` (needs `OLD_ENCRYPTION_KEY`, the new key is
  `.env`'s): dry run, refuses on unreadable values, prerekey backups, one
  transaction per database, verification, idempotent. Covers the three
  encrypted columns and the checkpoint payloads. Procedure and warnings in
  ARCHITECTURE ("Encryption key: backup, loss and rotation"). Rehearsed on a
  copy of the real database (11 values). **The real key was rotated on
  2026-09-20**: 11 values re-encrypted, the old key reads 0 of 11, the new key
  is in `.env` only (0 tracked files, 0 commits). Two local safety-net files
  remain until the owner deletes them: `.env.pre-rekey` and
  `data/backups/channelagent-prerekey-*.db` (see #67).
- gitleaks: `.gitleaks.toml` (two exact values allowed), `.gitleaks-baseline.json`
  (the c8a9eaa finding), CI job `secret-scan`. Locally: `docker run --rm -v
  "$PWD":/repo zricethezav/gitleaks:latest detect --source /repo --redact
  --config /repo/.gitleaks.toml --baseline-path /repo/.gitleaks-baseline.json`.
  gitleaks does not catch a key under an unrelated variable name; the
  Fernet-shape test in `tests/test_no_committed_secrets.py` does.
- **Priority rule from the user (2026-09-20): finish every ticket of a
  priority before starting a lower one** (all P1 before any P2). #55 (P2) was
  started and set aside: its tests are drafted outside the repo. Only P1 work
  remains open in the sense of "owner steps": the real key rotation, the live
  checks of #61, and the epics #6 (needs #29) and #35.


## P2 in order, after all P1 (2026-09-20)

P1 is finished on the code side (the real key was rotated, see #67); what is
left in P1 is the owner's decision to close and the epics. P2 resumed in
numeric order: **#55** implemented (unreadable values shown as
`<undecryptable>`, counted in `/storage`, one warning per minute); on the
real database read with the old key it counted exactly 11. Next in order:
#58, #59, #63; #62 is an owner decision and #29 was set aside.


## P2 tier of the plan (#72), 2026-09-20/21

Done in numeric order, each with a status comment and numbers in its issue:
#58 API auth hardening (committed `caad542`), then uncommitted: #59 admin
events (`admin_events`, actor `api`/`console`, encrypted details, log reads
recorded), #63 `reset_conversation`, #68 file permissions (`umask 077`,
warning on loose existing files, `start.sh` creates `.env` as 600), #69
dependency lock (`requirements.in` -> `requirements.txt`, resolved in
`python:3.12-slim` by `scripts/update_requirements.sh`, `pip-audit`).
`pytest` 590 passed.

- **CI is disabled at the owner's request** (`gh workflow disable`, state
  `disabled_manually`, file unchanged). The last run (`caad542`) had 2 of 3
  jobs failing because of #58; tracked in #73. Re-enable with `gh workflow
  enable 361230655` only after #73. Until then the secret scan of the
  history is run by hand (command above).
- New encrypted column = also add it to `app/admin/rekey.py::APP_COLUMNS`
  and `service._ENCRYPTED_COLUMNS` (a test fails otherwise). #59 found the
  rotation tool would have missed `admin_events.details`.
- Owner steps left: #62, `chmod` of the existing real files (#68), the
  phase 0 items of #72, real live checks (#61).
- Tooling: the RTK hook rewrites `sed -i` and breaks it on macOS, and
  `grep` output is summarised: use Python for edits and mutations.

## Session of 2026-09-21 (evening): independence, plan, admin API, models, agent settings

**Direction set by the owner.** An independent, 100% local, multi-user agent (no path, model or
reference outside the repository), extensible through MCP servers (mandatory), administered through
one secure API of which `start.sh` (full command line) and a friendly admin UI are the two clients.
Plan and comparison with another local agent project: `docs/COMPARISON_AJEAN.md`; designs:
`docs/API_SECURITY.md`, `docs/MCP_EXTENSION.md`, `docs/API_COVERAGE.md`. Epics #106 (admin API and
UI) and #107 (MCP); 25 sub-issues (#108 to #132), #133, and five under #104 (#134 to #138).
P1 working order set by the owner: #108, #109, #104, #110, #105, #115 to #117, #114, #113, #111, #112.
Security points S1 to S5 (`docs/API_SECURITY.md`) are deferred by the owner.

**Committed and pushed** (`5898141..6123616`):
- #103 (`d78a769`): model and `llama-server` bundle moved into `models/` and `vendor/llama.cpp/`,
  every mention of the earlier project removed, a test that keeps it that way; Docker build context
  4.95 GB to 3.97 MB; the live engine restarted from the new paths (55 s of interruption).
- #108 (`521391b`): a declared scope on every route, default deny, Host, Origin, size and time
  protection, error ids, strict schemas. Authorization matrix, now 38 routes x 4 scopes.
- #133 (`7acef08`): `/whoami`, `/status`, paging with `X-Total-Count`, tags, documented errors,
  `API_VERSION`.
- #109 (`4718a92`): command line generated from the routes (`--describe`, `--api`), jobs, `/config`,
  `/backups`, actor `cli:<user>`, engine started with a cleared environment. `--status` and `--stop`
  stay in bash on purpose (host scope, #111); restore and rekey are not API operations yet.
- #104 (`6123616`) with #134 to #138: outbound guard, model list, delete, import and pull as jobs,
  no network at inference. Measured on the real machine: import of a 986,048,576-byte blob and pull
  of a 491,400,032-byte model with matching SHA256, a pull interrupted at 50% and resumed, a chat
  turn with 0 connections outside the machine.

**Working tree, not committed** (#110): four agent settings (`system_prompt` encrypted, `model`,
`memory_mode`, `tools`), migration `b11c1796e218` checked on a copy of the real database (upgrade,
`alembic check`, downgrade, upgrade all exit 0), applied by the graph at each turn; 1281 tests
passed. It also carries the fix of a red test on the pushed commit `6123616`: the dev scripts held the
throwaway test key (`test_no_committed_secrets` refuses it in tracked files); they now generate one.

**Defects found while implementing** (all fixed, in the issue comments): an outbound guard that
judged multicast and NAT64 or 6to4 addresses carrying a private address as public; a symlink in
`models/` that would have made a delete remove its target; service errors shown as "Internal
error" in failed jobs; `start.sh --api` reaching the engine through `host.docker.internal`; tests
and scripts that ran turns on the real default database once `run_turn` read its agent.

**Working method that held**: implement one issue, run the targeted tests, disable each control in
turn (mutation check) and add a test for every survivor, validate on the real machine, post a status
comment with numbers on the issue, leave it open. Commit and push only when the owner says so.

**Owner steps**: the earlier project's copy of the model and the engine bundle are gone (removed by
the owner) and the container was rebuilt and recreated from the tree at `527c4be` (image `152a1e0bc63b`,
healthy 7 s after the start, the real database migrated to `b11c1796e218` with users 2, agents 3, action
logs 28 unchanged). Left for the owner: the decision on closing issues.
