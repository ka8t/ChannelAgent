"""Created the sub-issues of the 2026-09-21 plan (#108 to #132). Kept as a record: running it again
would create the issues again, so it is not meant to be re-run.
"""
import subprocess, json, sys
REPO="ka8t/ChannelAgent"
E106="Part of epic #106 (designs: `docs/COMPARISON_AJEAN.md` \"Design rule\", `docs/API_SECURITY.md`)."
E107="Part of epic #107 (design: `docs/MCP_EXTENSION.md`)."
COMMON_DONE="- Targeted tests of the touched files: N passed, 0 failed; `ruff check .` clean; full suite once before the commit (count quoted)."
I=[]
def add(key,title,labels,parent,scope,done,ui,order=None):
    I.append(dict(key=key,title=title,labels=labels,parent=parent,scope=scope,done=done,ui=ui,order=order))

# ---------------- epic 106, P1 ----------------
add("sec","API security baseline: a declared scope on every route, default deny, secrets masking, error format, body limits, Host and Origin checks",
 "P1-high,area:security,area:api,enhancement",E106,
 """Requirements of `docs/API_SECURITY.md` sections 4.1, 4.3, 4.5 and 4.6, without S1 to S5 (deferred by the owner).
- Four scopes `read`, `operate`, `admin`, `owner` declared on every route; a route without one stops the startup (default deny). The existing admin key acts as `owner` until named accounts exist (deferred).
- `Host` allow-list (`ALLOWED_HOSTS`) and `Origin` check on state-changing requests; no CORS headers.
- Strict request schemas (`extra="forbid"`, bounded lengths), body size limit (1 MB default), request timeout.
- Configuration read masks every secret, secret writes are write-only; `ENCRYPTION_KEY` is never readable and never settable through a generic route (only the rekey job changes it).
- Errors return a short stable message and an error id; details go to the redacted log. No path, SQL or stack in a response. Access log without bodies.""",
 """- Authorization matrix generated from OpenAPI: R routes x 4 scopes, 0 unexpected statuses (R quoted).
- Startup with one route lacking a scope exits non-zero (exit code and message quoted).
- Foreign `Host`: HTTP 421 or 400; foreign `Origin` on a POST: 403; a 2 MB body: 413 (statuses quoted).
- An induced internal error returns an error id and no path, SQL or traceback (test); the same id is in the log.
- Configuration read returns masked values; grep of every response body in the tests for the test secrets prints 0 lines.
- Mutation check per control: disabling it makes exactly its test fail.
"""+COMMON_DONE,"Not applicable: internal control; the UI inherits it.",1)
add("single","The API as the single entry point: start.sh client, in-process transport, jobs, describe, contract tests",
 "P1-high,area:api,area:tooling,area:admin-cli,enhancement",E106,
 """`docs/COMPARISON_AJEAN.md` \"Design rule\" points 1 to 7.
- `python -m app.admin.client` (run in the virtualenv `start.sh` prepares) turns each command into an API call; JSON output next to readable text; `./start.sh --describe --json` prints the manifest from OpenAPI.
- The bash-only logic moves behind the API: `--show-config`, `--set` (rules #74, #75, #80), `--status`, `--stop`. Bash keeps `.env`, virtualenv, `docker compose`, process launching.
- In-process ASGI transport when the application is stopped: restore, rekey, migrations and read-only commands use the same handlers.
- Long operations are jobs: id, status, progress, cancel.
- Actor `cli` plus the OS user in the admin events (#59).
- Launched processes get a cleared environment: measured 2026-09-21, the `llama-server` started by `start.sh` inherited every secret of `.env` (started now without them, 0 secret variable names in its environment).""",
 """- `./start.sh --describe --json` lists N commands and N equals the number of API routes (contract test: N passed, 0 failed).
- For each operation the script's JSON equals the HTTP response body: N compared, 0 differences.
- With the application stopped, read-only commands return the same JSON as with it running on the same database: diff empty (quoted).
- Mutation: a route without a script command makes exactly 1 contract test fail; `tests/test_start_*.py` pass unchanged (count quoted).
- A `llama-server` launched by the script has 0 secret variable names in its environment (`ps eww`, count quoted).
- A job started, polled and cancelled through both the script and HTTP (statuses quoted).
"""+COMMON_DONE,"This issue is what makes every later screen possible (generic forms from OpenAPI).",2)
add("agentcfg","Per-agent configuration: model, system prompt, memory mode, enabled tools",
 "P1-high,area:database,area:langgraph,area:admin-cli,enhancement","Standalone; prerequisite of #105 (model per agent), persistent memory (memory mode) and the MCP epic #107 (enabled tools).",
 """`Agent` has only `id`, `user_id`, `name`, `is_active`, `created_at` (`app/db/models.py`). Add `system_prompt`, `model` (nullable, default model when empty), `memory_mode` (`off`, `ondemand`, `always`, `search`), and an allow-list of tools (JSON, empty = none). Alembic migration with `batch_alter_table` (SQLite), migration backup first (#66). Service layer, API and script operations; the graph reads them per turn.""",
 """- Migration upgrade, downgrade, upgrade on a copy of the real database; `alembic check` clean (exit codes quoted); row count of `agents` unchanged.
- Two agents of the same user answer with different system prompts (test); an invalid `memory_mode` is refused with 422 (status quoted).
- Every new column that may hold sensitive text is registered as the project rule requires (`APP_COLUMNS`, `_ENCRYPTED_COLUMNS`) or documented as not sensitive.
"""+COMMON_DONE,"Manageable from the admin UI (#106): the agent screen edits all four fields (generic form).",4)
add("hostc","Host-side helper serving the host scope of the API (start, stop, restart, restore and rekey with the application stopped, files under models/)",
 "P1-high,area:security,area:docker,area:tooling,enhancement",E106,
 """Requirements of `docs/API_SECURITY.md` 4.7: a fixed table of operations with typed arguments, argument lists and no shell, off by default and started only by `start.sh` when enabled, loopback or Unix socket, calls signed with HMAC over method, route, body hash, timestamp and nonce (refused after 30 s or on a reused nonce), the application forwards a host call only after its own authorization, an audit event before and after each call, an admin notification for destructive ones (#53). Transport decided per platform and tested on Docker Desktop (Mac first, as the project rule requires) and on a Linux engine.""",
 """- A replayed request, an unsigned one and an operation outside the table are all refused (statuses quoted).
- Restore and rekey run from the API on a copy of the real database with the application stopped and restarted by the helper; row counts per table before and after equal (quoted).
- With the helper off, `lsof` shows 0 listening sockets for it (count quoted).
- Audit rows: 2 per call (before and after) (rows quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): stop, start, restart and restore or rekey with progress.",11)
add("uifound","Admin UI foundation: session login, layout, CSRF, CSP, vendored assets, generic forms rendered from OpenAPI, screens for existing entities",
 "P1-high,area:api,area:security,enhancement",E106,
 """D8 confirmed by the owner: server-rendered pages (Jinja2 and vanilla JavaScript), every asset vendored, no CDN, no Node. Interim login: the existing admin key through a server-side session (`__Host-` cookie, `HttpOnly`, `Secure`, `SameSite=Strict`, idle 30 minutes, absolute 8 hours, id rotated at login); CSRF token; `Content-Security-Policy` with nonces and no inline script; `nosniff`, `no-referrer`, `no-store`; text from channel users always rendered as text. Generic forms and result views from the OpenAPI manifest, hand-written screens only for log search and access requests. Screens: users, access requests, agents, logs, admin events, storage. New dependencies (Jinja2) go through the lock (#69).""",
 """- 0 external URLs in templates and static files (`grep` count quoted).
- A forged cross-site POST returns 403; the 6th wrong login in one minute returns 429 (statuses quoted).
- CSP, `nosniff`, `no-store` present on every authenticated response (test, N responses checked).
- A channel message containing a script tag and an event-handler attribute appears only as escaped text on every screen (test).
- Every route has a UI reach: contract test N of N, 0 unreachable.
- The dependency lock builds and the image starts (`docker build` exit code quoted).
"""+COMMON_DONE,"This issue is the UI.",12)
# ---------------- standalone P1 ----------------
add("backup","Scheduled backup of the database and the checkpoints with retention and status",
 "P1-high,area:database,area:tooling,enhancement","Standalone (gap E2 of `docs/COMPARISON_AJEAN.md`).",
 """Measured 2026-09-21: the only copy of the database is taken before a migration (`app/db/backup.py`); 0 scheduled backups. Add a scheduler (default daily, `BACKUP_INTERVAL_HOURS`, `BACKUP_KEEP`), the verified SQLite backup used by `make_backup`, the checkpoints file included, pruning by date (as #81), status in `--status` and the API, an admin notification when a backup fails (#53).""",
 """- With the interval set to 1 minute in a test, K backups are created and pruned to `BACKUP_KEEP` (counts quoted).
- Each backup opens and `PRAGMA integrity_check` returns `ok` (quoted).
- A failed backup (read-only target) raises 1 admin notification and shows in the status (quoted).
- A restore (#76) from a scheduled backup ends with equal row counts per table (quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): status, interval, keep count, run now.",10)
add("memory","Persistent memory per user and per agent: memory tools and modes",
 "P1-high,area:database,area:langgraph,enhancement","Standalone; depends on the tool loop (MCP 1/7) and per-agent configuration (`memory_mode`). Gap A3 and A4 of `docs/COMPARISON_AJEAN.md`.",
 """Search, read, add, edit and delete memory entries as tools of the loop, stored in the database in encrypted columns (registered in `APP_COLUMNS` and `_ENCRYPTED_COLUMNS`), scoped to (user, agent), so purge (#50), backup and rekey cover them. Modes `off`, `ondemand`, `always` (index injected), `search` come from the agent configuration.""",
 """- Memory survives a restart of the application (test with a real database file).
- Purging a user deletes their memory: 0 rows left (count quoted); another user's memory is unreadable through the tools (0 rows returned).
- The four modes change what is injected and which tools exist (test per mode).
- The rekey and its dry run count the new columns (numbers quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): browse, edit and delete a user's memory entries, each action an admin event.",9)
# ---------------- epic 107 ----------------
add("mcp1","MCP 1/7: tool-calling foundation (server flag, capability check, tool loop, benchmark)",
 "P1-high,area:langgraph,enhancement",E107,
 """Measured 2026-09-21 (`docs/MCP_EXTENSION.md` section 2): with `--skip-chat-parsing` a tool call comes back as text (`tool_calls` empty); without it `tool_calls` is filled. The flag is in `start.sh` and `docker-compose.prod.yml` with no recorded reason (cause not established). Measure the other effects of removing it, then remove it. Startup capability check: a probe request must return a parsed `tool_calls`, otherwise tools are disabled with a clear log line. Tool loop in the graph: rounds cap, identical-call guard, cancel with the turn, results truncated and labelled as data. Benchmark of tool selection.""",
 """- Effect of the flag: the existing conversation tests run against a server without it, N passed, 0 failed; the replies to M scripted prompts compared with and without it (M and the differences quoted).
- The flag is absent from `start.sh` and `docker-compose.prod.yml` (`grep` prints 0 lines).
- Capability probe: a server without parsing disables tools with 1 log line (test).
- Loop: at most R rounds per turn (R stated); the 3rd identical call is not executed again (counter 1); cancelling the turn stops a running tool within S seconds (measured).
- Benchmark on the real model, N scripted tasks at T = 1, 5, 10, 20 exposed tools: tool-selection accuracy and argument-validity rate per T (table quoted).
"""+COMMON_DONE,"Not applicable to the foundation; the enabled tools are per-agent (see per-agent configuration).",6)
add("mcp2","MCP 2/7: MCP client and server registry",
 "P1-high,area:langgraph,area:database,area:api,enhancement",E107,
 """`mcp` 1.30.0 (owner decision M6). Registry in the database: name, transport, command and arguments or exact URL, environment variables in encrypted columns, egress label (`local`, `lan`, `internet`), enabled flag, timeouts, allow and deny lists. Transports: stdio for vetted built-in servers, streamable HTTP on an exact-URL allow-list (M1). Manager: lazy connection, idle stop, restart with backoff, concurrency and result-size caps; one failing server never stops the others. Catalogue `mcp__<server>__<tool>` converted to OpenAI tools, per-agent allow-list. Child processes get a cleared environment. Admin operations in the API. One vetted built-in server (time) shipped and tested. The lock (#69) gets PyJWT, httpx-sse, python-multipart, sse-starlette and `mcp`.""",
 """- End to end: a Telegram message makes the agent call the built-in server's tool and answer from the result; the action log has exactly 1 row for the call (row quoted).
- One stdio server and one HTTP server each answer a call (log rows quoted).
- A server that exits, sleeps past the timeout or returns 10 MB: the turn answers within the timeout, other servers keep working (timings quoted).
- A child process environment contains 0 of the application's secret variable names (count quoted).
- The dependency lock builds on `python:3.12-slim` and the suite passes (count quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): add, test (lists the tools), enable, per-tool switch.",7)
add("mcp3","MCP 3/7: permissions, confirmation in the channel, audit, definition pinning",
 "P1-high,area:security,area:langgraph,enhancement",E107,
 """Default deny: a user reaches a tool only if granted, per agent and per server or tool. Policy per tool `allow`, `confirm`, `deny` (M4: `confirm` for destructive, open-world and unannotated tools). Confirmation asked in the same channel (Telegram button, email reply) with a timeout. Every call audited: user, agent, server, tool, redacted arguments, outcome, size, duration. Tool definitions hashed at approval; a change disables the tool until an administrator approves the diff. Shared credentials only with a shared flag and an owner grant (M5).""",
 """- A user with no grant gets a refusal and the server's call counter stays 0 (quoted).
- An unannotated tool asks for confirmation and is refused after the timeout (quoted).
- Changing one tool description on the server disables that tool until re-approval (test).
- 1 audit row per call; arguments containing a test secret are stored redacted (grep 0 lines).
"""+COMMON_DONE,"Manageable from the admin UI (#106): grants, policies, definition diff and approval, call history.",8)
add("mcp4","MCP 4/7: sidecar container isolation for third-party servers",
 "P2-medium,area:security,area:docker,enhancement",E107,
 """M2: third-party servers run as sidecar containers over streamable HTTP on the internal network: own filesystem, non-root, read-only, CPU and memory limits, network only as the egress label allows, image pinned by digest. Deploying one is a host operation of the host helper from an allow-list of digests. The application never gets the Docker socket.""",
 """- A sidecar server cannot read `data/` or `.env` (read attempt fails, output quoted).
- Deploy through the helper of an allow-listed digest succeeds; a non-listed image is refused (statuses quoted).
- The application container has 0 mounts of the Docker socket (`docker inspect` count quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): deploy, stop and remove a sidecar server.",None)
add("mcp5","MCP 5/7: skills (MCP prompts, local SKILL.md folders, load_skill)",
 "P2-medium,area:langgraph,enhancement",E107,
 """M3: both. MCP prompts a server publishes become user commands. Local skills are folders with a `SKILL.md` (name, description, instructions, needed tools); only names and descriptions enter the system prompt, the body is loaded by a `load_skill` tool; managed by administrators, versioned, granted per agent.""",
 """- 100 skills add fewer than N prompt tokens (N stated, measured count quoted).
- A skill body is loaded only when `load_skill` is called (test: 0 bodies in the prompt otherwise).
- A skill not granted to an agent is not listed and not loadable (test).
"""+COMMON_DONE,"Manageable from the admin UI (#106): create, version and grant skills.",None)
add("mcp6","MCP 6/7: tool-budget routing per intent",
 "P2-medium,area:langgraph,enhancement",E107+" Depends on #105 and MCP 1/7.",
 """Expose only the relevant subset of tools per turn (rules first, as #105), and route tool-heavy turns to a more capable model when the benchmark of MCP 1/7 shows the small model degrades.""",
 """- With 20 tools installed, a turn exposes at most T (value from the benchmark) and the prompt is smaller by P tokens (numbers quoted).
- Accuracy on the benchmark with routing is at least the accuracy at T = 5 without it (both quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): the intent to tool subset mapping.",None)
add("mcp7","MCP 7/7: prompt-injection policy and per-agent exposure view",
 "P2-medium,area:security,enhancement",E107,
 """A turn that read untrusted content through a tool and then reaches for a tool with write or internet reach requires confirmation. The admin sees, per agent, the combination of private data access, untrusted content sources and outbound reach.""",
 """- A scripted turn (fetch a page, then call a write tool) triggers a confirmation before the second call (test).
- The exposure view flags an agent holding all three (test on a fixture).
"""+COMMON_DONE,"Manageable from the admin UI (#106): the exposure view.",None)
# ---------------- P2 ----------------
add("uistep2","Admin UI second step: status, backups, configuration, models, restore and rekey with progress",
 "P2-medium,area:api,enhancement",E106+" Depends on the UI foundation and the host helper.",
 """Screens for engine status, backups (list, create, restore), configuration (read masked, write per the rules), models (list, pull, import as jobs with progress and cancel), restore and rekey through the helper.""",
 """- Restore and rekey done from the UI on a copy of the real database: row counts per table equal before and after (quoted).
- A 4.9 GB model pull shows progress and can be cancelled (status codes quoted).
"""+COMMON_DONE,"This issue is UI.",None)
add("telem","Live engine status and usage telemetry (per user, agent, model)",
 "P2-medium,area:api,area:langgraph,enhancement",E106,
 """Status from the engine's `/props` and `/slots` (loaded model, context, slots); telemetry computed from the action log: messages, failed turns, latency p50 and p95, tokens per user, agent and model over a period.""",
 """- The counts equal a direct SQL count on the same database (both numbers quoted).
- Status shows the model and context reported by `/props` (values quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): status and telemetry screens.",None)
add("export","Admin conversation export, itself audited",
 "P2-medium,area:api,area:security,enhancement",E106,
 """Export of one user's thread (Markdown and JSON) with decrypted text only on request, `admin` scope and above, one admin event per export.""",
 """- The export contains N messages and N equals the database count (quoted); 1 admin event row (quoted).
- A lower scope gets 403 (status quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): export button on the conversation screen.",None)
add("ratelimit","Rate limit and quota per user",
 "P2-medium,area:channels,area:security,enhancement",E106,
 """D9: the same limits for everyone, values in `.env` (messages per minute, simultaneous turns), validated by the settings rules. A refused message gets a short reply and is logged. One local engine serves everyone, so one flooding user must not starve the others.""",
 """- With a limit of L per minute, message L+1 gets the refusal text and 1 log row; a second user is unaffected (both quoted).
- An invalid value is refused by `--set` (exit code quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): the limits are configuration.",None)
add("retention","Retention of stored messages and logs, with a dry run",
 "P2-medium,area:database,area:security,enhancement",E106,
 """Configurable retention for messages, action logs and checkpoints; dry run lists counts per table; a backup is taken before a real run; an admin event records it.""",
 """- Dry run counts per table, then the real run deletes exactly those rows (before and after counts quoted).
- A backup exists before the run and 1 admin event row is written (quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): retention settings and a run with dry run.",None)
add("sched","Scheduled tasks: cron, every, daily, with the result sent back on the channel",
 "P2-medium,area:channels,area:langgraph,enhancement","Standalone; depends on the tool loop (MCP 1/7). Gap A14 and E6.",
 """Per-user tasks with cron, every-N and daily forms, per-user timezone, a global pause switch, ownership by user, the result delivered on the user's channel. Administration of every user's tasks.""",
 """- A task due in 1 minute runs once and its result is delivered (log rows quoted); after pause, 0 runs.
- A user cannot list or edit another user's task (test, 0 rows returned).
- Schedules parse or are refused with 422 (statuses quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): list, pause, run now, stop any user's tasks.",None)
add("recall","Recall archive of dropped turns and compaction of old tool results",
 "P2-medium,area:langgraph,enhancement","Standalone; complements #86; depends on MCP 1/7. Gaps A6 and A7.",
 """Lexical search over turns that fell out of the window (zero dependency), and shedding of long old tool results before the summary call.""",
 """- A fact stated 200 turns earlier is found by the recall tool (test); the archive is per (user, agent).
- A 20 KB tool result older than the window is replaced by a marker and the prompt shrinks by P tokens (quoted).
"""+COMMON_DONE,"Not applicable: internal.",None)
add("fetch","Local page fetch with the private-address guard",
 "P2-medium,area:langgraph,area:security,enhancement","Standalone; reuses the outbound guard of #104. Gap A8 (search deferred, D1).",
 """Readability extraction and HTML to Markdown (library chosen at implementation and locked), page cache, size and time caps, the guard: `https` only, private, loopback and link-local addresses refused after DNS resolution and on every redirect. Exposed as a tool through the loop.""",
 """- `http://`, `https://127.0.0.1`, a redirect to a private address and a page over the size cap are all refused (statuses quoted).
- A public page returns Markdown of at least N characters (quoted).
"""+COMMON_DONE,"Manageable from the admin UI (#106): allow-list of hosts.",None)
add("enginekey","Bearer key for the inference engine",
 "P2-medium,area:security,area:tooling,enhancement","Standalone. Gap B5.",
 """`LLAMA_SERVER_API_KEY` passed to `llama-server` (`--api-key`) and sent by the graph, validated by the settings rules, masked in `--show-config`, redacted in logs. Matters for the production topology where the engine is a separate container.""",
 """- Without the key the engine answers 401; the application with the key gets 200 (statuses quoted).
- `grep` of the logs for the key prints 0 lines.
"""+COMMON_DONE,"Manageable from the admin UI (#106): configuration.",None)
add("backupexp","Password-protected export and import of a backup for off-machine storage",
 "P2-medium,area:database,area:security,enhancement","Standalone. Gap C4 (decision D5, no relay).",
 """A single file holding the database and the checkpoints, encrypted with a key derived from a password (stdlib memory-hard function), for storage outside the machine; import into an empty directory.""",
 """- Export then import: row counts per table equal (quoted); a wrong password fails (exit code quoted).
- `grep` of the file for a known sentinel value prints 0 lines.
"""+COMMON_DONE,"Manageable from the admin UI (#106): export and import as jobs.",None)
# ---------------- P3 ----------------
add("small","Small adaptations: reasoning parameters, /export and /new commands, repetition detection, benchmark script",
 "P3-low,area:langgraph,area:channels,enhancement","Standalone. Gaps A16, A18, A19, A20, B4.",
 """(a) Pass reasoning parameters to the engine and strip a thinking block from channel replies (the installed model emits none, so nothing is broken today). (b) `/export` for a user's own conversation. (c) `/new` to start a fresh thread. (d) Repetition detection: a degenerate loop is cut and handled as a failed turn (#51). (e) `scripts/dev/bench_gateway.py` measuring tokens per second.""",
 """- (a) A mock reply with a thinking block reaches the user without it (test).
- (b) `/export` returns the user's own N messages (quoted). (c) `/new` gives a thread with 0 prior messages (quoted).
- (d) A 20-token sequence repeated 5 times is cut and logged as a failed turn (test).
- (e) The script prints tokens per second over 3 runs against the live gateway (values quoted).
"""+COMMON_DONE,"Not applicable, except (a) as configuration.",None)

nums={}
for it in I:
    body=f"{it['parent']}\n\n"+(f"**Working order in P1: {it['order']} of 12** (owner, epic #106 comment).\n\n" if it['order'] else "")+f"## Scope\n{it['scope']}\n\n## Done when\n{it['done']}\n\n## Admin UI\n{it['ui']}\n"
    r=subprocess.run(["gh","issue","create","--repo",REPO,"--title",it['title'],"--label",it['labels'],"--body-file","-"],input=body,text=True,capture_output=True)
    url=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    n=url.rsplit("/",1)[-1] if url else "ERR:"+r.stderr[:200]
    nums[it['key']]=n; print(it['key'],n,it['title'][:70]); sys.stdout.flush()
json.dump(nums,open("/private/tmp/claude-501/-Users-mac-Documents-Code-ChannelAgent/aae95f61-660b-469c-8e99-2170f827c38a/scratchpad/nums.json","w"))
