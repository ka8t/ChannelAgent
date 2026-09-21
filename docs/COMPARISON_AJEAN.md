# Comparison with AJEAN (2026-09-21)

Compared repository: `/Users/mac/Documents/Code/ajean` (Go, one binary, single user,
web UI, `llama.cpp` built locally). Goal: list what AJEAN does that ChannelAgent
does not, and decide which features are kept, **without giving up independence**
(100% local, no SaaS API key, no third-party relay).

Sections A to D compare the agent, engine, security and system features; section E compares the administration. Nothing here is decided yet. Every row has a recommendation; the owner decides.
Issues are created only for the rows marked **Keep** after the owner's decision.

## Reading guide

- **In CA**: state in ChannelAgent today, checked on the current tree
  (`app/graph.py`, `app/channels/*`, `app/db/backup.py`, `.env.example`, issue list).
- **Independence**: `local` = no external service; `SaaS` = needs one (rejected as is).
- **Verdict**: **Keep** (adopt), **Adapt** (adopt with a local equivalent or a
  different design), **Reject** (with the reason), **Covered** (already done).
- **Effort**: S (under a day), M (a few days), L (a week or more).
- Rule from the owner: installation and system features are rejected unless they
  adapt to ChannelAgent easily.

## Key finding

ChannelAgent's agent is a plain chat loop: history window plus a running summary
(#86, #87), no tools, no long-term memory, no scheduling, text only. AJEAN's value is
almost entirely in what surrounds the model (tools, memory, scheduler). Its
hardware, install and single-user UI parts do not carry over.

## A. Agent capabilities

| ID | AJEAN feature (source) | In CA | Independence | Verdict | Effort | Notes |
|---|---|---|---|---|---|---|
| A1 | Tool-calling loop against the OpenAI-compatible server (`llm_client.go` `runChat`, `EnabledTools`) | none | local | **Keep** | M | Foundation of A2, A3, A8, A9, A13. Needs a model that supports function calling; capability check against the real `llama-server`. |
| A2 | Loop guard: identical repeated call answered from the first result, escalating note, then no payload (`repeatedCallResult`, `dedupableTool`); tool run cancelled with the turn | none | local | **Keep** | S | Ships with A1. Also bound the number of tool rounds per turn (AJEAN removed its cap, so we choose one). |
| A3 | Persistent Markdown memory: `mem_search/read/add/edit/delete`, `MEMORY.md` index (`mem_store.go`, `mem_index.go`) | none (only checkpoints + summary) | local | **Keep** | M-L | Scoped per user and per agent, stored in the database and encrypted with Fernet (not loose files), so purge (#50) and backup cover it. |
| A4 | Memory modes off / ondemand / always / search (`MEM_MODE`) | none | local | **Adapt** | S | Per-agent setting, follows A3. |
| A5 | Projects = separate memory namespaces (`projects.go`) | agents per user (#37) | local | **Covered** | none | An agent already is a namespace. No new feature. |
| A6 | Recall archive: lexical search over turns dropped by compaction (`chat_recall.go`, zero dependency) | summary only (#86) | local | **Keep** | M | Complements #86: the summary loses detail, the archive can be searched. Pairs with A3. |
| A7 | Compaction sheds old long tool results before calling the model; reminds which memory pages were read (`chat_compact.go`, `chat_mem_pinned.go`) | window plus summary | local | **Adapt** | S | Only useful once A1 exists (tool results in history). |
| A8 | Local page fetch: readability extraction, HTML to Markdown, page cache, `web_open/read/grep` (`web_fetch_go.go`) | none | local | **Keep** | M | Python equivalents exist (trafilatura or readability-lxml). Multi-user context needs a guard AJEAN does not need: no fetch of private addresses (SSRF), size and time caps. |
| A9 | `web_search` through DuckDuckGo HTML scraping (`duckduckgoSearch`) | none | third-party site, no key | **Adapt** | S-M | Fragile and a third-party dependency. Local option: SearXNG container (own instance, still queries public engines). **Decision needed** (D1). |
| A10 | Shell, file write and edit tools on the host (`runShell`, `fileWrite`, `fileEdit`) | none | local | **Reject** | - | Any user of a Telegram or email channel would run commands. Not adaptable safely in a multi-user service. Revisit only as admin-only inside a sandbox (see D2). |
| A11 | Browser control over CDP (`computer_cdp.go`, `computer_use.go`) | none | local | **Reject** | - | Needs Chrome in the image, large attack surface, same multi-user objection as A10. |
| A12 | Images in chat, `see_image` (`chat_vision_tool.go`) | text only | local | **Reject for now** (owner, 2026-09-21: no multimodal use) | - | Reopen if a multimodal model is adopted. With B8 it would become one more route (image attached, vision model). |
| A13 | MCP client, stdio and HTTP transports (`mcp_client.go`, `mcp_config.go`) | none | local | **Keep** | M | Official Python `mcp` SDK. Servers configured by an admin only, enabled per agent; stdio servers run a process on the host, so never user-supplied. |
| A14 | Scheduled tasks: cron, every, daily (`tasks.go`, `tasks_cron.go`) | none | local | **Keep** | M | Best fit with channels: the agent sends its result back on Telegram or email at the chosen time. Per-user timezone, global pause switch, ownership by user. |
| A15 | Web push notifications, VAPID (`push.go`) | none | local (browser vendors relay it) | **Reject** | - | Made for a browser UI. Channels already deliver messages. |
| A16 | Reasoning mode and budget passed to the engine, visible reasoning (`REASONING*`) | not handled | local | **Adapt** | S | Pass the parameters, and strip the thinking block from channel replies (a leaked `<think>` in a Telegram message is a defect risk today). **To verify** on the real model. |
| A17 | Dated data tracker tool (`trackerTool`) | none | local | **Reject** | - | Niche; A3 memory covers the need. |
| A18 | Conversation export in Markdown or JSON (`chat_export.go`) | admin console and API only | local | **Adapt** | S | A `/export` command for a user's own conversation. Depends on the export rules for encrypted content. |
| A19 | Several saved sessions, new session, favorites | agent switch (#37), admin reset (#63) | local | **Adapt** | S | A user command to start a fresh thread (`/new`). |
| A20 | Detects degenerate model output (repetition loops) and cut streams (`llm_repeat_test.go`, `streamCutError`) | failed turn handling (#51, #93) | local | **Adapt** | S | Repetition detection is not covered today. |

## B. Engine and models

| ID | AJEAN feature | In CA | Independence | Verdict | Effort | Notes |
|---|---|---|---|---|---|---|
| B1 | Presets and one-click model switching (`backend_presets.go`) | one `LLAMA_SERVER_URL` | local | **Reject** | - | Model management belongs to `llama-server` or Ollama. Not adaptable without owning the engine. |
| B2 | Builds `llama.cpp` per machine: CUDA, ROCm, Metal, Vulkan (`backend_build.go`, `backend_gpu*.go`) | native Mac `llama-server` and Docker prod (Ollama or vLLM) | local | **Reject** | - | Hardware and engine build are out of scope. |
| B3 | Model download from Hugging Face (`backend_models.go`, `HF_TOKEN`) | manual: the owner puts a `.gguf` in `MODELS_DIR` and sets `MODEL_FILE` | hub contacted once, on an explicit admin action | **Adapt** (revised 2026-09-21) | M | First rejected as SaaS; that was too strict. Independence is about runtime: weights fetched once, then nothing external at inference. See B7 and D6. |
| B7 | Choose a model and download it from the console (new for CA; AJEAN has the download only) | none | local after download | **Keep** | M | Admin command and API: list installed models, pull `<repo>[:quant]` or a URL, or import a local file. Resumable, SHA256 check, never at inference time, token optional and never logged (#82). |
| B8 | Switch model by intent, **without llama-swap** (not in AJEAN, which switches presets by hand) | one model, one `LLAMA_SERVER_URL` | local | **Keep** | L | The installed `llama-server` (build 10976) has a native router mode: `--models-dir`, `--models-preset`, `--models-max`, load on demand by the request's `model` field. Ollama and vLLM also take `model` per request, so production works the same way. ChannelAgent only decides which `model` a turn uses. Design in "Model routing" below. |
| B4 | Bench tok/s (`llm_bench.go`) | none | local | **Adapt** | S | A script in `scripts/dev/` measuring the gateway, not a product feature. |
| B5 | Bearer key protecting the inference engine (`set-api-key`) | none | local | **Keep** | S | `LLAMA_SERVER_API_KEY` sent by the graph; useful for the production topology where the engine is a separate container. **To verify** it is not already possible through a header setting (no such setting found in `.env.example`). |
| B6 | OpenAI-compatible endpoint exposed to third-party tools | none | local | **Reject** | - | Not the purpose of ChannelAgent, adds an attack surface. |

## C. Security and data

| ID | AJEAN feature | In CA | Independence | Verdict | Effort | Notes |
|---|---|---|---|---|---|---|
| C1 | Encryption key lives only in the browser; server keeps a fingerprint | Fernet key in `.env`, server side | local | **Reject** | - | Channels have no browser to hold a key. The server must decrypt to answer. |
| C2 | Envelope encryption: one data key wrapped by several key-encryption keys (password, recovery key), rotation without re-encrypting data (`mem_vault.go`) | one Fernet key; rotation re-encrypts every row (#74, #78, #102) | local | **Adapt** | L | Would make rotation instant and add a recovery key. Large migration on real data, benefit is moderate. **Decision needed** (D4). |
| C3 | Snapshots of memory before risky operations, with rotation (`mem_snapshots.go`) | migration backup and restore (#66, #76, #81) | local | **Covered** | none | Memory (A3) would live in the same database, so the existing backups apply. |
| C4 | Password-encrypted backup bundle, restore from password (`backup_bundle.go`) | plain SQLite copies (sensitive columns encrypted) | local (upload to relay is SaaS) | **Adapt** | M | Keep the local encrypted bundle, drop the relay upload. Lets the owner store a backup off the machine safely. **Decision needed** (D5). |
| C5 | Encrypted remote access through `ajean.link` relay (`relay_*.go`) | SSH tunnel and TLS proxy recipes (#60, #91, #92) | **SaaS** | **Reject** | - | Third-party relay. |
| C6 | Access key on the control API, first-run key | `API_SERVER_KEY` with hardening (#58) | local | **Covered** | none | |
| C7 | Firewall rule and LAN exposure switch (`sys_network.go`) | bind address and port publishing (#52) | local | **Covered** | none | |

## D. Installation and system (rejected unless easy to adapt)

| ID | AJEAN feature | Verdict | Reason |
|---|---|---|---|
| S1 | systemd, launchd and Windows service install (`sys_service_*.go`, `sys_install_*.go`) | **Reject** | Docker restart policy and the autoheal overlay (#89) do the job; native mode is `start.sh`. |
| S2 | Self-update from GitHub releases with SHA256 check (`sys_update.go`) | **Reject** | Deployment is an image rebuild. GitHub as update source is also an external dependency. |
| S3 | Tray icon, splash screen, Windows first-run, console handling | **Reject** | Desktop features, no server equivalent. |
| S4 | Configuration editor `ajean edit`, state in bbolt | **Covered** | `start.sh --show-config` and `--set` (#34, #75, #80). |
| S5 | Migration from older data layout (`migrate_07.go`) | **Covered** | Alembic (#11). |
| S6 | i18n of the UI (`tools/verify-i18n`, `TRANSLATING.md`) | **Reject** | English-only project rule, no end-user UI. |
| S7 | Live logs command | **Covered** | Log search (#39). |
| S8 | Cross-platform build (six binaries) | **Reject** | Not applicable to a Python container. |

No installation or system feature qualifies as easily adaptable, so none is kept.

## Model routing (B8) and model management (B7)

Measured on 2026-09-21 against the installed binary
(`llama-server` build 10976, commit 987498f45): `--models-dir`, `--models-preset`,
`--models-max N` and `--models-autoload` exist; `--hf-repo` and `--model-url` exist.
`MODELS_DIR` currently holds one model (`Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`,
4,692.8 MB), so a second model is needed to test routing (see the issue's
"Done when").

Serving layer: the engine loads and unloads models. ChannelAgent never starts or
stops engine processes, which is what llama-swap would do.

Decision layer, in ChannelAgent, in this order, first match wins:

1. Explicit choice: the user's `/model <name>` command, or the model set on the agent
   (#37).
2. Rules: message properties known without a model (length, presence of an
   attachment, a command prefix, tool use required once A1 exists).
3. Optional classifier: one cheap call to a small model returning a label
   (chat, code, summarize...). Off by default, because it adds a call and possibly a
   model swap to every turn.
4. Default model.

The mapping intent to model is admin configuration stored in the database, not code.

Impacts found in the current code (`app/graph.py`, `.env.example`):

- `LLAMA_CTX_SIZE` is one global value and drives the history budget
  (`HISTORY_CONTEXT_SHARE`, #47, #87). It has to become a per-model value, read from
  the router's model listing when possible.
- Summaries (#86) and checkpoints are model-independent, so a thread can change
  model between turns.
- Load time on a swap is unmeasured on this Mac; `--models-max` keeps N models
  resident, bounded by unified memory. Both numbers go in the issue's "Done when".
- Every model name reaches the log and the failed-turn path (#51), so an unknown or
  failed-to-load model must fall back to the default and be recorded.

Model management (B7): `./start.sh` and the admin console list installed models
(from `MODELS_DIR` or the router's listing), pull a model by `<repo>[:quant]` or URL,
or import a local file. No curated catalog: it would go stale and would be
invented knowledge; the owner names what to pull. The hub is contacted only when an
admin asks; nothing external happens at inference.

## Decisions (owner, 2026-09-21)

- **D1, web search backend (A9): accepted.** No search at first, page fetch only.
  SearXNG container later if search is wanted.
- **D2, host shell and files tool (A10): accepted.** Rejected for good.
- **D3, images (A12): no multimodal use for now.** Rejected for now.
- **D4, envelope encryption (C2): accepted.** Keep the current Fernet key and the
  rotation tooling (#74, #78, #102). C2 rejected.
- **D5, encrypted off-machine backup (C4): accepted.** Local password-protected
  export and import, no relay.

## Open decisions (answer here)

**Answered by the owner on 2026-09-21 (recommendations accepted): D8 confirmed; D10 target
kept, deferred with S1 to S3, interim login by the admin key and a session; D11 option (c);
D9 same limits for everyone; the API issues come before #104.** Details in the comment of
epic #106. The entries below keep the original options for the record.

- **D6, model download source (B7).** Options: (a) any Hugging Face repo or direct URL
  plus local import, admin action only; (b) local import only, no network. The
  hub is a public third party, contacted once per model. Recommendation: (a), because
  the owner asked for automatic download, and (b) stays possible by simply not using
  the pull command. Done when: a pull of a small public model completes with a
  SHA256 match, an interrupted pull resumes, and no network call happens during a
  chat turn (checked by running a turn with the network blocked).
- **D7, intent classifier (B8 step 3).** Options: (a) no classifier, steps 1, 2 and 4
  only; (b) classifier with a small model. Recommendation: (a) first. Add (b) only
  if rules prove too coarse on real conversations, with a measured extra latency
  per turn.

## E. Administration

Measured 2026-09-21. AJEAN: 138 distinct `/api/...` endpoints behind a 12,047-line web
page (`internal/ajean/ui/`). ChannelAgent: 22 Admin API routes (`app/api/routes.py`), a
6-entry terminal console (`app/admin/cli.py`) and the `start.sh` commands `--show-config`,
`--set`, `--status`, `--stop`, `--admin`, `--restore`, `--rekey`.

The two are not the same kind of admin. AJEAN administers a personal appliance (engine,
models, presets, tools, memory, tasks). ChannelAgent administers a multi-user service
(who may talk to it, on which channel, with which agent, and what happened). On governance
ChannelAgent is ahead: roles and permissions, access requests with approve and deny,
an audit trail of what administrators did (#59), log search, guided restore and key
rotation. AJEAN has none of that because it has one user. On operability ChannelAgent is
behind, and the gaps below are measured on the current tree.

| ID | Gap (AJEAN reference) | In CA today | Verdict | Effort |
|---|---|---|---|---|
| E1 | Per-agent configuration: system prompt, model, memory mode, enabled tools (`/api/sysprompt`, `/api/preset`, `/api/tools/toggle`, `/api/memory`) | `Agent` has `id`, `user_id`, `name`, `is_active`, `created_at` only (`app/db/models.py`); nothing to configure | **Keep** | M. Hinge of both works: #105 needs a model on the agent, A3 and A4 need a memory mode, A13 needs enabled tools. |
| E2 | Automatic scheduled backup with retention and status (`/api/backup/auto`, `backup/status`, `StartBackupScheduler`) | copy of the database only before a migration (`app/db/backup.py`); 0 scheduled backups | **Keep** | S-M. The only protection of the real database between migrations is what the owner remembers to run. |
| E3 | Live status: engine, loaded model, RAM and VRAM, tok/s (`/api/status`, `/api/ram`, `/api/vram`, `/api/bench/last`) | `--status` says up or down for the app, the API and the engine | **Adapt** | S-M. Engine details from `llama-server` `/props` and `/slots`; no VRAM probe (Mac unified memory, VPS CPU). |
| E4 | Usage telemetry (`/api/telemetry`) | none: 0 metrics or counters in `app/` | **Adapt** | M. Per user, agent, model: messages, failed turns, latency, tokens, computed from `ActionLog`; a console screen and one admin endpoint. |
| E5 | Admin API parity with the terminal tools: backups list, create, restore, config view (`/api/backup/*`, `/api/config`) | restore, rekey, config only through `start.sh` | **Adapt** (now derived from the operation registry, see the design rule) | M. Lets the owner administer over the SSH tunnel (#60, #91) without a shell on the host. Read-only config with secrets masked; writes stay in `start.sh`. |
| E6 | Task administration: list, pause, run, stop (`/api/tasks/*`) | no tasks | **Keep** | With A14. Console and API to list every user's tasks, pause all, stop one. |
| E7 | Conversation export for the admin (`/api/chat/export`) | log search only | **Adapt** | S-M. Export of one user's thread, itself recorded as an admin event (#59), decrypted only on request. |
| E8 | Web administration UI that manages everything (owner, 2026-09-21: "l'ui de l'admin doit permettre de tout gerer") | none | **Keep** (reversed) | L. Third front on the existing service layer (`app/admin/service.py`), after the API covers everything (E5). See D8, D10, D11. |
| E9 | Rate limit and quota per user | none: 0 matches for rate limit or quota in `app/` | **Keep** (not in AJEAN, which has one user) | M. One local engine serves every user, so one flooding user starves the others. |
| E10 | Retention of stored messages and logs (not in AJEAN) | none: logs and history grow without a limit (only storage overview, #40) | **Keep** | M. Configurable retention with a dry run and an admin event; personal data should not live for ever. |
| E11 | Model and preset administration (`/api/models/*`, `/api/presets/*`) | none | **Keep** | Covered by #104 and #105. |
| E12 | Update check and apply, tray, service log endpoint | image rebuild, Docker logs | **Reject** | Same reasons as section D. |

## Design rule: the API is the single entry point (owner, 2026-09-21)

Owner, first statement: "le script start.sh est la verite et doit permettre de tout gerer, de
l'admin a la configuration complete. L'ui admin est son reflet en mode friendly, sans ligne de
commande. Une modification sur le script ne doit pas casser l'ui admin."
Owner, refinement: "afin d'avoir un meme comportement script ou UI, il faut avoir un seul point
d'entree commun, l'API."

The refinement supersedes the wording "start.sh is the source of truth": **the API is the
truth; `start.sh` is its complete command-line client and the UI is its friendly client.**
`start.sh` still manages everything, from administration to the complete configuration, and the
UI still needs no command line. Two clients of one API cannot behave differently.

1. **One implementation per operation, behind the API.** Users, requests, agents, logs, storage,
   backups, restore, rekey, configuration read and write, status, models, and later tasks, memory,
   MCP, limits, retention. Each route carries metadata (needs the application stopped,
   destructive, host scope, output schema). The OpenAPI document with that metadata is the
   manifest; there is no second registry.
2. **`start.sh` is a thin client.** A small Python client (`python -m app.admin.client`, run in
   the virtualenv `start.sh` already prepares) turns each command into an API call and prints the
   JSON result, or a readable text from it. The bash-only logic of today (`--show-config`,
   `--set`, `--status`, `--stop`, value quoting and rules #74, #75, #80) moves behind the API.
   Bash keeps only what has to exist before an API does: creating `.env`, the virtualenv,
   `docker compose`, launching processes.
3. **The API is reachable in three ways, with the same routes and the same code.**
   - HTTP to the running application (loopback for the script, the tunnel or TLS proxy for a
     remote administrator, #60, #91, #92);
   - in process, through an ASGI transport, when the application is stopped: the script calls
     the same handlers without a server. Restore, rekey, migrations and every read-only command
     work with the application down;
   - the host scope, served by a small host-side helper, for what cannot run in the container:
     starting, stopping and restarting the application or the engine, the stop and start around a
     restore or a rekey, files under `models/`. It exposes only routes of the same API (never a
     free shell), on loopback or a Unix socket, with its own token in `.env`. The application API
     forwards host routes to it, so the UI and the script still see one API.
4. **Long operations are jobs.** Pulling a model, restoring, rotating the key: the API returns a
   job id; status, progress and cancel are routes. The UI shows progress, the script waits and
   prints it.
5. **Identity and audit.** The script authenticates with a local token from `.env` (mode 600) and
   its admin events (#59) record the actor as `cli` with the operating-system user; the UI records
   the named administrator (D10). Same audit trail for both.
6. **The UI is generated from the manifest**: forms and result views rendered from OpenAPI, and
   hand-written screens only where a generic view is not enough (log search, access requests).
   A new route appears in the UI, and in the script's command list, without client code.
7. **A change to the script cannot break the UI, and the reverse**, because they share nothing
   but the API. Contract tests in the full suite:
   - every route has a script command and is reachable from the UI (rendered form or declared
     host operation); a route without them fails the test;
   - for each operation the script's JSON output equals the HTTP response body (same handler);
   - the OpenAPI document is snapshotted: a changed signature or schema fails until the snapshot
     and the client tests change together; the manifest carries a version, and a client that
     meets an unknown one says so and refuses to act;
   - with the application stopped, a read-only command returns the same JSON as with it running,
     on the same database.

Limits, stated: the steps that bring the API up (`.env`, virtualenv, `docker compose up`) cannot
go through it and stay in bash; they are the only exception.

## Decisions (owner, 2026-09-21, second batch)

- **D6 and D7**: recorded in #104 and #105 (pull from a hub or URL on explicit admin action;
  no classifier at first).

## Open decisions (answer here)

- **D8, web administration UI (E8): decided by the owner.** It must manage everything. Design
  proposal, to confirm: server-rendered pages (Jinja2 plus a little vanilla JavaScript), every
  asset vendored in the repository (no CDN, no Node toolchain, so independence holds), each
  screen calling the same service layer as the API and the console. No business logic in the UI.
  Rule that keeps "everything" true over time: every new feature issue has a "manageable from the
  admin UI" line in its Done when.
- **D10, how an administrator signs in to the UI.** Today one static key protects the API (#58).
  A browser needs more: a session, CSRF protection, a strict Content-Security-Policy, a login
  rate limit. Options: (a) one admin key typed at a login page, session cookie; (b) named admin
  accounts with hashed passwords, so the admin events (#59) say who did what. Recommendation:
  (b), reusing the users table with an admin role (#13), because an audit trail that cannot tell
  two administrators apart is weaker than the one the project already built. The UI stays
  reachable only through the SSH tunnel or the TLS proxy (#60, #91, #92), never published.
- **D11, host-level operations (revised twice after the owner's rules).** Some
  operations cannot run inside the application container by nature: restoring a backup and
  rotating the key (the application must be stopped, #76, #78), starting, stopping or
  restarting the application or the engine, and anything under `models/` (on the host).
  The owner wants no command line at all, so showing the command to copy is not enough.
  Options: (a) the UI covers what runs inside and prints the command for the rest; (b) as (a)
  plus a bind mount of `models/`; (c) a small host-side helper, started by `start.sh`, serving the host scope of
  the same API (never a free shell), bound to the loopback
  interface or a Unix socket, authenticated with its own token kept in `.env`, every call
  recorded as an admin event (#59). Recommendation: **(c)**, changed from (b) because the
  owner's requirement excludes (a) and (b). Its size is bounded because it is the same
  registry, executed on the host. Restore and rekey run through it with the application
  stopped by the helper itself, and the UI shows the progress.
- **D9, rate limit policy (E9).** Options: (a) per user messages per minute and a cap on
  simultaneous turns, the same for everyone; (b) per role. Recommendation: (a) with the values
  in `.env`, refused messages answered with a short text and logged.

## Priority plan (proposed, issues created after the owner's validation)

Strict tiers, as the project rule requires. Within a tier the order below is the proposed
working order; numbers are issues that already exist.

**P0**
- #103 independence from the earlier project: implemented, waits for two owner actions.

**P1** (a feature missing that the owner asked for, or data at risk)
1. #104 model management (list, pull, import).
2. E1 per-agent configuration (model, system prompt, memory mode). New issue; #105 depends on it.
3. #105 routing by intent through `llama-server` router mode.
4. A1 with A2 (tool-calling loop and guard) and A13 (MCP client), now epic #107: mandatory,
   design in `docs/MCP_EXTENSION.md`, first issue also removes the `--skip-chat-parsing` flag
   after measuring its effect.
5. A3 with A4: persistent memory and its modes. New issue.
6. E2 scheduled backup with retention. New issue.
7. The API as single entry point: routes with operation metadata, in-process ASGI transport for
   the stopped application, jobs for long operations, the `start.sh` client (`--describe` from
   OpenAPI), the bash-only logic moved behind the API, the contract tests above. New issue;
   the next two depend on it. Existing `start.sh` tests (`tests/test_start_*.py`) must keep
   passing unchanged.
8. **Deferred by the owner (2026-09-21): S1 to S5 later.** Named administrators, scoped tokens,
   sessions with step-up authentication (`docs/API_SECURITY.md` S1 to S3), audit chain (S4),
   refusal of remote exposure without a TLS proxy (S5). Interim: the UI signs in with the
   existing admin key. Not lost: kept in `docs/API_SECURITY.md` and in the project memory.
9. Host-side helper serving the host scope of the API (D11 (c)), with the signed-call and
   allow-list requirements of `docs/API_SECURITY.md` 4.7. New issue.
10. Admin UI foundation (D8, D10): login and session, layout, CSRF and CSP, vendored assets,
   generic forms and views rendered from OpenAPI, hand-written screens for users, access
   requests, agents, logs, admin events, storage. New issue, under epic #106.

**P2**
- A14 scheduler with E6 task administration.
- A6 recall archive, A7 compaction of tool results.
- A8 page fetch with the private-address guard.
- (A13, the MCP client, moved to P1 under epic #107.)
- Admin UI, second step: status, backups, configuration, models, restore and rekey through the
  helper with progress. New issue, same epic.
- E3 live status, E4 usage telemetry, E7 admin conversation export.
- E9 rate limit and quota (D9), E10 retention.
- B5 engine key, C4 encrypted export of a backup.

**P3**
- A16 reasoning parameters and stripping the thinking block (to verify on a model that emits
  one; the installed Llama 3.1 8B does not, so nothing is broken today).
- A18 `/export`, A19 `/new`, A20 repetition detection, B4 benchmark script.

Issues per item, not per line of this document, and only for the rows above: about 25 issues
if everything is kept (one epic for the UI and two issues under it; each feature issue carries
its own "manageable from the admin UI" line instead of a separate UI issue). Accepted limits stay in the status comment of the issue they concern.

Not kept after the decisions: A5, A9 (deferred), A10, A11, A12, A15, A17, B1, B2, B6, C1, C2,
C5, E12 and all of section D of the tables (installation and system).

## Issue map (created 2026-09-21)

API completeness for generated clients: #133 (P1). The routes each issue must add:
`docs/API_COVERAGE.md` section 5.

Epics: #106 (admin API and UI), #107 (MCP). P0: #103. P1 in the owner's working order: #108 API
security baseline, #109 API as single entry point, #104 models, #110 per-agent configuration,
#105 routing, #115 to #117 MCP 1/7 to 3/7, #114 persistent memory, #113 scheduled backup, #111
host helper, #112 UI foundation. P2: #118 to #121 MCP 4/7 to 7/7, #122 to #126 admin, #127 tasks,
#128 recall and compaction, #129 page fetch, #130 engine key, #131 encrypted backup export. P3:
#132 small adaptations.
