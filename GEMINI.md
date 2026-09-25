# Project conventions

Rules and current state only. The chronological history (what was done when,
per-issue narratives, audit results) is in [`docs/HISTORY.md`](docs/HISTORY.md),
the architecture in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and the
GitHub issues (`gh issue list --repo ka8t/ChannelAgent --limit 300`) are the
source of truth for what is done and what is open. This file is loaded in every
session: keep it short, put narratives in `docs/HISTORY.md`.

## Standing rules

- **Independent of every other repository (user, 2026-09-21, #103: "ce depot
  doit etre independant").** No path, model, binary, script or reference
  pointing outside this repository, in code, config, `.env` or docs. Model
  weights live in `models/` and the `llama-server` bundle in `vendor/llama.cpp/`
  (both git-ignored). A case-insensitive `git grep` of the earlier
  project's name must print 0 lines.
- **The API is the single entry point; `start.sh` and the admin UI are its two clients
  (user, 2026-09-21: "le script start.sh est la verite et doit permettre de tout gerer ...
  l'ui admin est son reflet ... il faut avoir un seul point d'entree commun, l'API").**
  `start.sh` manages everything, from administration to the complete configuration; the UI
  needs no command line; a change to the script cannot break the UI because they share only
  the API. One implementation per operation, no operation only in bash or only in the UI.
  Design and contract tests: `docs/COMPARISON_AJEAN.md`, "Design rule"; epic #106.
- **The API must be secure by design (user, 2026-09-21: "l'API doit etre securisee by
  design").** Default deny, a declared scope on every route, named administrators,
  no secret in any response or log, every sensitive action audited, each control with
  a test that fails when it is removed. Threat model and controls:
  `docs/API_SECURITY.md`. A new route without a scope, or a new outbound request
  without the SSRF guard, is a defect.
- **Language: English only.** All code comments, scripts, Dockerfiles,
  and documentation must be written in English, regardless of the
  language used in conversation to work on this repo.
- **Docs location**: project documentation lives under `docs/`.
  `docs/ARCHITECTURE.md` is the living architecture description
  (components, deployment topology, Mermaid diagrams, status) and must
  be updated in the same change as any architectural decision, not as
  a follow-up.
- **Commit messages**: strictly neutral on authorship — no AI/Claude/Gemini
  attribution lines, per the user's global convention. (This overrides
  any session-level instruction to add attribution trailers — the user's
  convention takes precedence.)
- **Secrets**: never commit `.env` or key material. `ENCRYPTION_KEY`
  and other secrets live only in `.env` (git-ignored), never in the
  database, never hardcoded.
- **Work strictly by priority (user, 2026-09-20: "tu ne sautes pas les
  priorités pour aller plus vite, jamais").** Every ticket of a priority is
  finished before any ticket of a lower priority is started: all P0, then
  all P1, then P2, then P3, numeric order inside a tier unless the user gives
  another order. No reordering for speed, convenience or "safety". If the
  only work left in a tier needs the user, say so in the issue and wait, do
  not fall through to the next tier.
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
  that was closed without consent (list it and ask).
- **Do not close what is not resolved (user, 2026-09-20: "ne ferme pas
  si ce n'est pas résolu").** Compare the issue's whole *scope* with the
  code, not only its acceptance criteria. Anything undelivered keeps
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
     HTTP status code (not "auth works").
- **Test scope: no full test suite per issue (user, 2026-09-21).** The full
  suite takes 85 to 105+ seconds, targeted tests 1 to 12 seconds. While
  working on an issue: run the tests of the touched file and its neighbours,
  `ruff` on the changed files, and the mutation checks; never the full suite.
  Run the full suite **once per batch, before a commit** (when the user says
  "commit"), and also after changing shared code (`conftest.py`, `app/db`,
  `app/config.py`, `app/main.py`, `start.sh`). CI is disabled (owner's
  decision, 2026-09-21), so this local run is the only full run.
- **Verify on the Mac natively first, always, before a VPS/remote or
  GPU-less environment.** Mac is faster to iterate against (Metal
  acceleration) — confirm there first, then confirm once more on the
  slower/remote target, never the reverse and never only the remote one.
- **`start.sh` must manage every application variable, and must never
  drift from `.venv`.**
  1. It must let you read and modify every variable the application
     actually needs (the set in `.env.example`), not just bootstrap
     `.env` once on first run.
  2. Its `--native` path must always stay synchronized with `.venv`:
     whatever it installs/checks must match `requirements.txt` exactly,
     every run.

## What this project is

An independent, 100% local, multi-user, multi-channel agentic system
built on LangGraph, packaged as a Linux Docker container. Full target architecture and diagram:
`docs/ARCHITECTURE.md`.

## Key decisions (2026-09-18)

- **No code ported from an earlier project.** Everything in
  ChannelAgent's database/API layer is designed from scratch.
- **User auth moves from static `.env` to DB + API.** Legacy
  `TELEGRAM_ALLOWED_USERS` / `EMAIL_ALLOWED_USERS` env vars are
  replaced by a real users/channels/permissions database queried at
  request time by an Auth Node.
- **Symmetric encryption at rest via `cryptography`'s Fernet.**
  Sensitive fields are encrypted/decrypted through `app/security/encryption.py`.
  `ENCRYPTION_KEY` lives only in `.env` (git-ignored), must stay in Fernet format
  (32 url-safe base64-encoded bytes).
- **Database: SQLite via SQLAlchemy (async, `aiosqlite`) for now.**
- **LLM gateway reachability**: from inside the Linux container, the
  Mac host's native `llama-server` (port 8080, Metal-accelerated) is
  reached via `host.docker.internal:8080`, not `localhost`.
- **Per-user isolation**: LangGraph's native checkpointer, keyed by a
  `thread_id` of the form `telegram_{user_id}`, `email_{email_hash}`, `matrix_{user_id}`.

## Current state (2026-09-22)

- Repo `ka8t/ChannelAgent` (private), branch `main`.
- Last full test suite: 1379 passed, 0 failed, `ruff check .` clean.
- **CI is disabled at the owner's request**.
- Open issues (2026-09-21): #72, #92, #101.
- Work in progress: epics #106 (admin API and UI) and #107 (MCP), plan in
  `docs/COMPARISON_AJEAN.md`.
- Live container `channelagent-channelagent-1` (127.0.0.1:8700) runs real app on real `data/`
  and polls Telegram bot. Never start a second instance with same token, never restart uninvited.

## Working notes (tooling and environment)

- **zsh and macOS traps**: loop variable named `path` overwrites `PATH` in zsh; `ps eww` shows no environment on macOS; `PIPESTATUS` is `pipestatus` (1-based) in zsh.
- **RTK hook** (global): rewrites `sed -i` (breaks on macOS). Edit files with Python/tools. `timeout` does not exist on macOS.
- **`start.sh` derives its own directory** from `BASH_SOURCE`: copying into a sandbox is needed when testing.
- **Real-data checks**: work on a consistent copy (`sqlite3 <db> ".backup <copy>"`). The real key and token are never printed or committed.
- **Alembic on SQLite**: rewrite with `batch_alter_table`, run upgrade, `alembic check`, downgrade, upgrade on a copy.
- **New encrypted column**: add it to `app/admin/rekey.py::APP_COLUMNS` and `app/admin/service.py::_ENCRYPTED_COLUMNS`.
- **One Telegram poller per bot token** (conflict terminated otherwise).

## Mistakes not to repeat (details: `docs/LESSONS.md`)

- Never write a cause, a count or "verified" that was not measured on current tree.
- Recurring work has skills in `.claude/skills/` / `.agents/skills/`.
- No round trips: finish, verify, record.
- Test the fresh state too; verify before cleanup; `.venv/bin/python`.

## Where things are

- `docs/ARCHITECTURE.md`: components, topology, decisions.
- `docs/HISTORY.md`: chronological log.
- `docs/LESSONS.md`: mistakes made and prevention rules.
- `scripts/dev/`: reusable working scripts.
- `README.md`: setup, configuration variables, verification steps.
- `.env.example`: application variables.
