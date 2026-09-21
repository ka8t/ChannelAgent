# Project conventions

Rules and current state only. The chronological history (what was done when,
per-issue narratives, audit results) is in [`docs/HISTORY.md`](docs/HISTORY.md),
the architecture in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and the
GitHub issues (`gh issue list --repo ka8t/ChannelAgent --limit 300`) are the
source of truth for what is done and what is open. This file is loaded in every
session: keep it short, put narratives in `docs/HISTORY.md`.

## Standing rules

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
- **Work strictly by priority (user, 2026-09-20: "tu ne sautes pas les
  priorités pour aller plus vite, jamais").** Every ticket of a priority is
  finished before any ticket of a lower priority is started: all P0, then
  all P1, then P2, then P3, numeric order inside a tier unless the user gives
  another order. No reordering for speed, convenience or "safety". On
  2026-09-20 P2 tickets (#53, #54, #66) were done and #55 was started while
  P1 #67 was open: that was wrong. If the only work left in a tier needs the
  user, say so in the issue and wait, do not fall through to the next tier.
- **Trace every question in an issue, no pending confirmations in chat
  (user, 2026-09-20: "je ne veux pas de points en attente de
  confirmation. Je veux que tous les questionnements soient aussi tracés
  dans des issues").** Any gap, doubt, caveat, unverified check or design
  decision becomes an issue, or an "Open question(s) (answer here)"
  comment (options, recommendation, "Done when" with numbers) on the
  relevant issue. Reports end with what was done and where each remaining
  point is tracked, not with a list of questions. No "not covered" caveat
  without a linked issue.
- **NEVER close an issue without the user's explicit consent (user,
  2026-09-20: "ne prends JAMAIS de décision de fermer une issue sans mon
  consentement").** Closing is the user's decision, not the assistant's,
  even with complete evidence and green CI. When work looks done: post the
  evidence and a status comment on the still-open issue ("implemented,
  nothing pending, closing is the owner's decision") and leave it open;
  do not ask in chat. "Continue", "commit and push" and
  "ok for the plan" are not consent to close. This includes `gh issue
  close`, `Closes #N` keywords in commit messages, and reopening an issue
  that was closed without consent (list it and ask). On 2026-09-20 #45,
  #39, #40 and #52 were closed without consent; the user then had all
  four reopened, and they stay open until the user allows closing them. #43 and #44 were closed after a question that
  named the closing and got a "yes".
- **Do not close what is not resolved (user, 2026-09-20: "ne ferme pas
  si ce n'est pas résolu").** Compare the issue's whole *scope* with the
  code, not only its acceptance criteria: the 2026-09-20 audit reopened
  #3, #36, #37 and #41, which had passed their acceptance criteria while
  parts of their scope were never delivered. Anything undelivered keeps
  the issue open (finish it, or comment what remains, or split the rest
  into a new open issue). An epic closes only when every sub-issue and
  every "Done when" line is met and measured. Never close with a "not
  covered" caveat.
- **Never close a GitHub issue unless it is actually implemented and
  verified — and verification means numbers, not narrative.** Two
  rules from the user, the second sharpening the first (2026-09-18):
  1. A closing comment must describe a real check that was actually
     run (a test, a build, an end-to-end call) against the current
     code, not a description of intent. If re-checking a closed issue
     later finds the claim doesn't hold, reopen it — don't leave it
     closed and just fix the code silently.
  2. **"I ran it and it worked" is not proof by itself — cite exact
     figures.** User's own words: "tu fermes toujours les issues sans
     avoir de chiffres et de preuves formelles, je ne crois pas sur
     paroles. Je veux des faits." Every closing comment must include
     concrete, checkable numbers: `pytest: N passed, 0 failed` (not
     "tests pass"), an exact exit code (not "the build succeeds"), a
     row count from an actual query (not "the record was created"), an
     HTTP status code (not "auth works"). A prose description of what
     was checked is not sufficient on its own, even when the check was
     real — the reported number is the artifact that makes it checkable.
- **Test scope: no full test suite per issue (user, 2026-09-21).** The full
  suite takes 85 to 105 seconds (903 tests on 2026-09-21), targeted tests 1 to
  12 seconds. While working on an issue: run the tests of the touched file and
  its neighbours, `ruff` on the changed files, and the mutation checks; never
  the full suite. Run the full suite **once per batch, before a commit** (when
  the user says "commit"), and also after changing shared code (`conftest.py`,
  `app/db`, `app/config.py`, `app/main.py`, `start.sh`). Why it stays: on
  2026-09-21 the full run caught 22 `test_restore.py` failures that targeted runs
  never showed (the tests depended on a real `channelagent` Docker container
  running on the machine). A closing comment quotes the last full-suite number
  of the pushed commit; it does not re-run the suite for a number already
  measured on the same code. CI is disabled (owner's decision, 2026-09-21), so
  this local run is the only full run.
- **Verify on the Mac natively first, always, before a VPS/remote or
  GPU-less environment.** User's instruction (2026-09-18): the Mac is
  faster to iterate against (Metal acceleration) — confirm there
  first, then confirm once more on the slower/remote target, never the
  reverse and never only the remote one. Mirrors the legacy Hermes
  project's own documented "Mac first, then VPS" workflow convention
  — carried forward here as a binding rule, not just historical
  context. (#21's production-topology test followed this pattern
  correctly by using this Mac's own Docker Desktop rather than seeking
  out a real VPS — worth remembering as the template: local Docker's
  Linux VM often substitutes for "needs Linux," it doesn't have to
  mean "needs a remote machine.")
- **`start.sh` must manage every application variable, and must never
  drift from `.venv`.** Two standing requirements from the user
  (2026-09-18), binding on any future change to `start.sh`:
  1. It must let you read and modify every variable the application
     actually needs (the set in `.env.example`), not just bootstrap
     `.env` once on first run and leave the rest to manual editing.
     **Implemented** ([#34](https://github.com/ka8t/ChannelAgent/issues/34)):
     `--show-config` and `--set`, with value rules (#75, #80). Keep it
     complete when a variable is added.
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


## Current state (2026-09-21)

Facts, refreshed when they change; the issues have the detail.

- Repo `ka8t/ChannelAgent` (private), branch `main`. Telegram and Email
  adapters are live; Matrix (#29) and a dedicated bot mailbox (#42) were set
  aside by the owner on 2026-09-21.
- Last full test suite: 1030 passed, 0 failed (120 s), `ruff check .` clean
  (2026-09-21, on cef5596).
  Targeted runs while working; the full suite once per batch, before a commit
  (see "Test scope").
- **CI is disabled at the owner's request** (`gh workflow disable 361230655`).
  Re-enable only when asked (`gh workflow enable 361230655`). Dependabot updates
  still run.
- Open work by tier: all P0 closed. P1: #6 (epic, needs #29), #72 (owner
  checklist), #84 (fixed and pushed, waits for the owner to close). P2: #29
  (set aside). P3 implemented and pushed (cef5596), each with a
  status comment and the closing left to the owner: #47, #48, #56, #57, #60,
  #64, #65, #70, #71 (this file), #77, #78, #85 and #93 (P2, found on the way); open points: #86 to #102.
  Set aside: #42. #61 has its quoted results (checks 4 and 7 not run live, by
  the owner's decision).
- The owner's live container `channelagent-channelagent-1` (127.0.0.1:8700)
  runs the real app on the real `data/` and polls the real Telegram bot. Never
  start a second instance with the same token, never restart it uninvited.
- Owner-side leftovers: delete `.env.pre-rekey` and
  `data/backups/channelagent-prerekey-*.db` once the encryption key is stored
  in a password manager; rebuild the container to pick up new images.

## Working notes (tooling and environment)

Learned the hard way, none of it derivable from the code. Context in
`docs/HISTORY.md`.

- **RTK hook** (global): rewrites `sed -i` (breaks on macOS) and summarises
  `grep` and `docker logs` output. Edit and mutate files with Python; use
  `rtk proxy <cmd>` for raw output. `git status --short | grep -c .` counts
  the tool's own "ok" line. `git rev-parse --short A B` fails: one ref per call.
- **zsh**: an unquoted `$VAR` is not word-split (a `docker run $E` with several
  `-e` options passed one argument). Write the options out. `timeout` does not
  exist on macOS; use the tool's timeout or `gh run watch`.
- **`start.sh` derives its own directory** from `BASH_SOURCE`: to test it in a
  sandbox, copy the script into the sandbox; `cd`-ing elsewhere still edits the
  real `.env`.
- **Real-data checks**: starting the console or the app applies pending
  migrations, so a "read-only" check against `data/` can change it. Work on a
  consistent copy (`sqlite3 <db> ".backup <copy>"`) or open with `?mode=ro`.
  The real key and token are never printed or committed.
- **Alembic on SQLite**: autogenerate omits `import app.db.types` for
  `EncryptedString` columns and emits ALTERs SQLite rejects for foreign keys and
  dropped columns. Rewrite with `batch_alter_table`, then run upgrade,
  `alembic check`, downgrade, upgrade on a copy of the real database.
- **New encrypted column**: add it to `app/admin/rekey.py::APP_COLUMNS` and
  `app/admin/service.py::_ENCRYPTED_COLUMNS` (a test fails otherwise).
- **One Telegram poller per bot token** (a second gives `Conflict: terminated`).
- **Docker Desktop's Linux VM** satisfies most "needs Linux" checks. A root-owned
  volume cannot be simulated with a named volume (Docker copies the image
  directory's owner); use `--tmpfs ...:uid=0`.

## Mistakes not to repeat (details: `docs/LESSONS.md`)

- Never write a cause, a count or "verified" that was not measured on the current
  tree; say "cause not established"; correct a wrong comment at once.
- Every script used is kept in `scripts/dev/` (index in its README); look there
  first. Explain "mutation" and other jargon in plain words.
- No round trips: finish, verify, record, and create an issue for every open
  point in the same turn. Test the fresh state, not only the existing one.
- Verify before cleaning up; use `.venv/bin/python`; low-entropy test values.

## Where things are

- `docs/ARCHITECTURE.md`: components, topology, every decision (kept current
  in the same change as the decision).
- `docs/HISTORY.md`: the chronological log this file used to hold.
- `docs/LESSONS.md`: mistakes made and the rule that prevents each.
- `scripts/dev/`: reusable working scripts (mutation runner, rehearsals, tools).
- `README.md`: setup, configuration variables, verification steps.
- `.env.example`: every application variable (`start.sh --show-config`, `--set`).
