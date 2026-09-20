# ChannelAgent Architecture

This is a living description of the system: components, deployment
topology per platform, and data flow. It is updated in the same change
as any architectural decision, not as a follow-up.

## Origin and goal

ChannelAgent replaces the Hermes Agent orchestrator (a deployment built
on the third-party `nousresearch/hermes-agent` Docker image, see
[Audit of the legacy Hermes project](#audit-of-the-legacy-hermes-project)
below) with an independent, 100% local, multi-user, multi-channel
agentic system built on LangGraph and packaged as a Linux Docker
container.

The central change from the legacy system: user authorization moves
from static `ALLOWED_USERS` environment variables to a proper database
and API layer, enabling per-user permissions, multiple administrators,
and runtime user management without editing `.env` and restarting the
service.

## System diagram

```mermaid
graph TD
    %% Inbound Channels Layer
    subgraph Channels [Inbound/Outbound Gateways]
        TG[Telegram Bot Adapter]
        EM[Email SMTP/IMAP Adapter]
        MX[Matrix/Element Client Adapter]
    end

    %% Central Router & Security Layer
    subgraph RouterLayer [Unified Event Router & Security]
        EV[Event Normalizer<br/>Schema: user_id, channel, text]
        AUTH[Guardrail & Auth Node]
        CRYPT[Application-Layer Encryption<br/>AES-256 / Fernet via .env key]
        DB[(Secure Database<br/>Encrypted Data-at-Rest)]
    end

    %% Core Agent Processing Layer
    subgraph LangGraphEngine [LangGraph Orchestrator]
        LG[State Graph Workflow]
        MEM[(MemorySaver / Checkpointer<br/>Isolated by thread_id)]
    end

    %% Compute Infrastructure Layer per Platform
    subgraph DeploymentTopology [Multi-Platform Compute Topologies]
        direction LR
        subgraph LocalMac [Local macOS Development]
            M1_GPU[Apple Silicon Metal Acceleration]
            LL_MAC[llama-server native Mac<br/>Port 8080 / Context 65536]
        end
        subgraph ProdVPS [Production VPS Linux Deployment]
            DOCKER_LLM[Containerized llama-server<br/>CPU threads, port 8080]
            LINUX_COMP[Linux CPU Acceleration]
        end
    end

    %% Data Flow Connections
    TG & EM & MX -->|Raw Event| EV
    EV -->|Normalized Data| AUTH
    AUTH <-->|Read/Write Hash & Cipher| CRYPT
    CRYPT <--> DB
    AUTH -->|If Authorized: Route to Thread| LG
    LG <-->|Persist Session State| MEM

    %% Compute Mappings
    LG -->|Local Dev API Calls via host.docker.internal:8080| LL_MAC
    LL_MAC <--> M1_GPU
    LG -.->|Production API Calls via internal network| DOCKER_LLM
    DOCKER_LLM <--> LINUX_COMP

    %% Return Path
    LG -->|Execution Output| Channels
```

## Components

### Channel adapters

Each adapter (Telegram, Email, Matrix/Element) is responsible only for
transport: receiving a raw platform-specific message and normalizing it
into the standard event schema before handing it to the router. Adapters
do not implement authorization or business logic themselves.

Normalized event schema:

```
{
  "user_id": str,     # platform-specific identifier (Telegram user id,
                       # email address, Matrix user id)
  "channel": str,     # "telegram" | "email" | "matrix"
  "text": str          # message content
}
```

### Email on a shared mailbox

The mailbox used by the Email adapter, `contact@codefixture.com`, is
shared. The website uses it to receive contact and information
requests, and the bot uses it to talk to its users. The adapter has to
tell an ordinary customer mail from a message meant for the bot, and it
must never disturb the ordinary ones.

**Rule (subject tag).** The adapter only handles messages whose subject
contains `EMAIL_TRIGGER_TAG` (default `[agent]`, case-insensitive, ASCII
only). A reply keeps the tag because the adapter answers with
`Re: <original subject>`, so a conversation continues without retyping
it.

| Incoming message | What the adapter does |
|---|---|
| No tag in the subject | Nothing. Not fetched, not flagged, not answered. It stays unread for a human. |
| Tag, sender authorized | Read, marked Seen, filed into `EMAIL_AGENT_FOLDER`, routed to the agent, reply sent. |
| Tag, sender unknown | Read, marked Seen, filed into `EMAIL_AGENT_FOLDER`, an `AccessRequest` is created for the admin. No reply is sent. |

How the guarantees are enforced (`app/channels/email.py`):

- The server-side `SEARCH UNSEEN SUBJECT "<tag>"` narrows the set, and
  the subject is checked again in the adapter because IMAP servers
  differ in how they match `SUBJECT`.
- Messages are fetched with `BODY.PEEK[]`, which sets no flag. Only a
  tagged message is then marked `\Seen`. A plain `RFC822` fetch marks the
  message as read on most servers, which is what hid customer mail from
  humans before this rule existed.
- An empty tag, or one with non-ASCII characters, quotes or backslashes,
  is refused: the adapter does not start. An empty tag never means
  "process everything".
- A handled message leaves the `INBOX` that humans read: it is moved to
  `EMAIL_AGENT_FOLDER` (default `INBOX.Agent`, the OVH/Dovecot layout with
  `.` as separator; created and subscribed on first use; empty value =
  leave it in the `INBOX`). Everything is addressed by IMAP UID, not by
  message number, because a move renumbers the messages after it. The
  move uses `UID MOVE` when the server and `imaplib` both support it,
  otherwise `UID COPY` + `\Deleted` + `UID EXPUNGE` (needs `UIDPLUS`),
  otherwise nothing is moved. A plain `EXPUNGE` is never sent, because it
  would also remove messages a human client flagged Deleted but has not
  expunged. A failed move is logged and never blocks the message from
  being handled. **Nothing is deleted or purged automatically**: this was
  an explicit decision (2026-09-20), messages are moved, never removed.
- Unknown senders get no reply on email (`SILENT_DENIAL_CHANNELS` in
  `app/channels/dispatch.py`). An email `From` address can be forged, so
  answering it would send mail to a third party.

**What email can do today.** A conversation with the user's default
agent. Creating or editing agents is done from the admin console
(`./start.sh --admin`) or the Admin API, not by sending a command by
mail: no message parsing for commands exists yet.

**The tag is a routing convention, not a security boundary.** Anyone can
type it. Access control is still the Auth Node: a tagged message from an
unknown sender only creates a pending request.

Tracking: the tag rule is [#43](https://github.com/ka8t/ChannelAgent/issues/43),
the folder is [#44](https://github.com/ka8t/ChannelAgent/issues/44).

**Future evolution
([#42](https://github.com/ka8t/ChannelAgent/issues/42)).** Give the bot
its own dedicated address, used only by the Email adapter. The tag is
then no longer needed to protect ordinary mail, and can be removed or
kept as an optional extra filter. This only needs the `EMAIL_*`
variables to point at the new mailbox, plus the decision about the tag.

### Event Normalizer and Auth Node

The Event Normalizer converts each channel's raw payload into the
schema above. The Auth Node then queries the database (through the
encryption layer) to check whether the `(channel, user_id)` pair is a
known, active, authorized user, and what permissions they hold. This
replaces the legacy `ALLOWED_USERS` static string check with a runtime
database lookup, allowing users and permissions to be added, revoked,
or scoped without restarting the container.

### Roles and permissions

A `User` (platform-independent) has one `ChannelIdentity` per
`(channel, external_id)` it's known by. `Permission` is a separate
table, not a column: each row is `(channel_identity_id, kind)` with
`kind` one of `chat` (may talk to the agent) or `admin` (may also
manage other users through the Admin API — see below). Granting is
inserting a row, revoking is deleting one; there is no third "no
permission" state to reconcile.

Permissions are scoped to the `ChannelIdentity`, not the `User` —
the same person can hold `admin` on their Telegram identity while
their Email identity only has `chat`, or none at all. The Auth Node's
decision (`app/security/auth.py::authorize`) is always evaluated
against the specific `(channel, user_id)` pair a message arrived on,
never against the user's permissions on other channels.

### Application-layer encryption

Sensitive fields (raw email addresses, Matrix access tokens, other
personal metadata) are encrypted before being written to the database
and decrypted after being read, using symmetric encryption
(`cryptography`'s Fernet, AES-128-CBC + HMAC under the hood). The
encryption key is loaded at runtime from `.env` (`ENCRYPTION_KEY`) and
is never stored in the database and never committed to Git. See
`app/security/encryption.py`.

### Database and migrations

SQLite via SQLAlchemy (async, `aiosqlite`) — matches the "100% local"
requirement with zero extra infrastructure. `DATABASE_URL` in `.env`
is the only thing that would change to move to Postgres later.

Schema changes are tracked with [Alembic](https://alembic.sqlalchemy.org/)
(`alembic/versions/`), not `Base.metadata.create_all` — `init_db()`
(`app/db/session.py`) runs `alembic upgrade head` at every startup, so
a schema change never requires dropping the database. See `README.md`'s
"Database migrations" section for the day-to-day workflow.

### LangGraph orchestrator

A single `StateGraph` workflow (`app/graph.py`, to be implemented)
handles agent reasoning and tool use for every channel. Per-user,
per-conversation isolation is achieved through LangGraph's native
checkpointer mechanism, keyed by a `thread_id` derived from the channel
and user identity, e.g.:

- `telegram_{user_id}`
- `email_{email_hash}` (hash, not the raw address, used as the thread
  key — the raw address itself is only ever handled encrypted at rest)
- `matrix_{user_id}`

### Compute topology

- **Local macOS development**: a native `llama-server` process runs
  directly on the Mac host (Metal acceleration), listening on port
  8080 with a 65536-token context. The Linux Docker container reaches
  it via `host.docker.internal:8080`, not `localhost`.
- **Production VPS**: a containerized `llama-server` (same binary, same
  flags as the Mac's — no `-ngl` GPU offload, CPU threads instead)
  serves inference over the internal Docker network, port 8080. See
  `docker-compose.prod.yml` and `docker/llama-server.Dockerfile`
  (#21). **Decided over Ollama/vLLM**, this diagram's original
  design, after auditing the legacy Hermes project's own production
  setup: Hermes previously ran `llama-swap` in front of `llama-server`
  for a "swap models at runtime" feature this project never uses, and
  `llama-swap`'s own separate, untracked update lifecycle let its VPS
  silently run a two-week-stale `llama-server` through a real
  incident. A single always-loaded model, containerized directly,
  needs none of that — and keeps the exact same OpenAI-compatible
  endpoint shape `app/graph.py` already talks to on the Mac, so dev and
  prod run identical inference code paths, not two.

The application code that calls the LLM gateway does not need to know
which topology it is running against — only the base URL
(`LLAMA_SERVER_URL`) changes between environments.

## Audit of the legacy Hermes project

Source directory audited: `/Users/mac/Documents/Code/Hermes`.

**Finding: there is no reusable database or API server source code to
port over.** The Hermes repository is a deployment and provisioning
wrapper around a third-party, closed-source base image
(`FROM nousresearch/hermes-agent:latest` in `docker/Dockerfile`), not a
project that contains its own server implementation. Concretely:

- No SQL files, migrations, or ORM schema definitions (Prisma,
  SQLAlchemy, or otherwise) exist anywhere in the repository. The only
  schema-adjacent file is `docker/patch-web-search-schema.py`, a
  build-time monkey-patch of a JSON-schema tool contract inside the
  vendored image — unrelated to a user/permissions database.
- The runtime SQLite files present (`state.db`, `kanban.db`,
  `runs_idempotency.db`, `response_store.db`, found under
  `macos-arm64/data/`) are created and owned by the vendored
  `hermes-agent` binary at runtime. Their schemas are not defined in
  this repository's source and are not safe or meaningful to copy —
  they belong to a different, closed application.
- **No API server source code exists for port 8645.** The `.env` files
  (`macos-arm64/.env`, `linux-x86_64-vps/.env.example`) only *configure*
  a port (`API_SERVER_PORT=8645`, `API_SERVER_ENABLED=true`,
  `HERMES_DASHBOARD=1`) for a dashboard/API component that ships inside
  the vendored `nousresearch/hermes-agent` image. There is no routing
  logic, endpoint definitions, or request handlers checked into this
  repository to analyze or reuse.
- **The `ALLOWED_USERS` mechanism is confirmed to be exactly what it was
  described as**: static environment variables per channel
  (`TELEGRAM_ALLOWED_USERS`, `EMAIL_ALLOWED_USERS`), read directly from
  `.env` by provisioning scripts (`configure-telegram.sh`,
  `configure-email.sh`, `provision-user.sh`) and documented in
  `shared/multi-user-agents.md`. There is no database-backed user table
  anywhere in the legacy repository — confirming this is a real gap
  ChannelAgent's database/API layer is designed to close, not a
  migration of an existing mechanism.

**Security note**: `macos-arm64/.env` (a real, non-example environment
file) contains a live `API_SERVER_KEY` value and a dashboard basic-auth
password. Neither was copied into this repository. If that key or
password needs to be reused or rotated, do so manually and outside of
version control.

**Practical consequence for this project**: the database schema
(users, channels, permissions, encrypted fields) and the admin API
described in this document are designed from scratch for ChannelAgent.
Nothing from Hermes is ported at the code level; only the operational
knowledge audited above (the `host.docker.internal:8080` local LLM
path, the channel set to support, and the static-`ALLOWED_USERS`
problem being solved) carries over.

## Status

- [x] Git repository initialized, `.gitignore` protecting `.env` and
      local databases.
- [x] Encryption helper placeholder (`app/security/encryption.py`) and
      settings loader (`app/config.py`).
- [ ] Everything else is tracked as GitHub issues on
      [`ka8t/ChannelAgent`](https://github.com/ka8t/ChannelAgent/issues),
      organized as 7 epics, one per section of this document:
      [#1 Encrypted database & models](https://github.com/ka8t/ChannelAgent/issues/1),
      [#2 Database-backed authorization](https://github.com/ka8t/ChannelAgent/issues/2),
      [#3 LangGraph orchestrator & state isolation](https://github.com/ka8t/ChannelAgent/issues/3),
      [#4 Containerization & deployment topology](https://github.com/ka8t/ChannelAgent/issues/4),
      [#5 Admin API](https://github.com/ka8t/ChannelAgent/issues/5),
      [#6 Channel adapters](https://github.com/ka8t/ChannelAgent/issues/6),
      [#7 Testing & CI](https://github.com/ka8t/ChannelAgent/issues/7).
      Each epic links its own implementation issues, labeled by
      priority (`P0-critical` .. `P3-low`) and area
      (`area:database`, `area:security`, `area:api`, `area:channels`,
      `area:langgraph`, `area:docker`, `area:testing`).
