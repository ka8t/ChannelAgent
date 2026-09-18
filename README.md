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

This repository is an early scaffold, not a runnable application yet.
See the checklist in `docs/ARCHITECTURE.md` ("Status") for what exists
and what's still missing (database models, admin API, channel
adapters, the LangGraph workflow itself, and the Dockerfile).

## Prerequisites

- Python 3.11+
- Docker (for the eventual container build — not required yet, see
  Status above)
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

```bash
./start.sh
```

There is no application entry point to run yet (`app/main.py` and the
Dockerfile don't exist — see Status above); `start.sh` currently stops
after preparing and validating the local environment.

## Verify

Once the local venv is set up, confirm the encryption layer loads
correctly:

```bash
source .venv/bin/activate
python3 -c "from app.security.encryption import encrypt_value, decrypt_value; t = encrypt_value('test'); assert decrypt_value(t) == 'test'; print('encryption OK')"
```

## Troubleshooting

- **`ENCRYPTION_KEY is missing or empty`** (from `start.sh` or
  `app/config.py`): generate one with the command under Configure
  above and set it in `.env`.
- **`llama-server is not reachable`** (macOS, from `start.sh`): start
  it natively on the Mac host first — this project does not manage
  that process. See the legacy reference script at
  `../Hermes/macos-arm64/scripts/run-llama-server.sh` if useful.
- **Fernet `ValueError: Fernet key must be 32 url-safe base64-encoded
  bytes`**: `ENCRYPTION_KEY` is in the wrong format — it must not be a
  hex string (e.g. a SHA-256 digest); it must be the base64 output of
  `Fernet.generate_key()` or the equivalent shown under Configure.

## Sources

- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [`cryptography`'s Fernet](https://cryptography.io/en/latest/fernet/)
