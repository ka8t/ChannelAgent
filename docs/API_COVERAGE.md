# Admin API coverage audit (2026-09-21)

Question: is the API available, and does it offer every function the UI and the script need?
Answer: available and complete for what exists today; incomplete for what is planned. This
document lists what was measured, what was added (#133), and the routes each open issue must
add so that the UI and `start.sh` can both do everything through the API (epic #106).

## 1. Availability (measured)

Live API on `127.0.0.1:8700` (container `channelagent-channelagent-1`, image built before #108):

| Call | Answer |
|---|---|
| `GET /users`, `/requests`, `/storage`, `/logs?limit=1`, `/admin-events?limit=1`, `/openapi.json`, `/docs` with the key | 200 (7 of 7) |
| `GET /nonexistent` with the key | 404 |
| `GET /users` without a key | 401 |
| `GET /users` with a foreign `Host` | 200 (the #108 protection is not in that image; it is active after the owner's rebuild) |
| operations in its OpenAPI | 25 |

The current code serves 27 operations (25 plus `/whoami` and `/status`).

## 2. Console against API (measured on the service layer)

`app/admin/service.py` has 35 public functions. 21 are used by the console; 24 by the API.
Every function the console uses is reachable through the API except two, neither a gap:

- `list_pending_requests`: `GET /requests?status=pending` returns the same list.
- `get_user_detail`: a composite of `GET /users/{id}`, `/channels`, `/permissions`, `/agents`; the UI
  assembles it from 4 calls. A composite route is added only if the measured round trips hurt.

The 12 functions with no API route and not used by the console are channel internals
(`record_action`, `request_access`, `resolve_agent`, `find_undelivered_answer`, ...), not
administration.

## 3. `start.sh` and the admin modules against API

| Operation | API today | Where it is planned |
|---|---|---|
| `--show-config`, `--set` | none | #109 (`/config`, masked) |
| `--status` | `/status` (added by #133) covers components, database, engine; the process check stays host-side | #133, #111 |
| `--stop`, start, restart | none (host operation) | #111 |
| `--restore` (list, check, run) | none | #109 (`GET /backups`), #111 (restore, host) |
| `--rekey` | none | #111 |
| backup create and list | none | #109 (`/backups`, job), #113 |
| models (`--models`) | none | #104 |

## 4. Contract quality, before and after #133

| Property a generated client needs | Before | After |
|---|---|---|
| operations with a description | 25 of 25 | 27 of 27 |
| operations with a tag (screen grouping) | 0 of 25 | 27 of 27 |
| operations documenting 401, 403, 429 | 0 of 25 | 27 of 27 |
| operations with an id documenting 404, changes documenting 409 | 0 | all |
| paging on simple lists (`limit`, `offset`, `X-Total-Count`) | none | `/users`, `/requests`, `/users/{id}/channels`, `/users/{id}/agents` |
| who am I (actor, scope, version) | none | `GET /whoami` |
| status (version, uptime, components, database revision and size, engine model and context) | none | `GET /status` |
| declared API version | FastAPI default | `API_VERSION` in `app/api/version.py` |

Not done, on purpose: totals for `/logs` and `/admin-events` (they already page with `limit` and
`offset`; a total needs a count query, add it if the UI needs page numbers there).

## 5. Routes each open issue must add (proposal)

Conventions for every new route: plural nouns; a declared scope (#108); documented errors and a
tag (#133); every long operation returns `202` and a job id (`/jobs`, #109); every change writes an
admin event (#59); configuration secrets are write-only (`docs/API_SECURITY.md` 4.6).

| Issue | Routes |
|---|---|
| #109 | `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`; `GET /config` (secrets masked), `PATCH /config` (the value rules of `settings_rules`); `GET /backups`, `POST /backups` (job) |
| #104 | `GET /models` (installed, and which one the engine loaded), `POST /models/pull` (job), `POST /models/import` (job), `DELETE /models/{name}` |
| #110 | no new route: `PATCH /agents/{id}` and `POST /users/{id}/agents` accept `system_prompt`, `model`, `memory_mode`, `tools` |
| #105 | `GET /routing`, `PUT /routing` (rules and default model) |
| #111 | `POST /host/stop`, `POST /host/start`, `POST /host/restart`, `POST /backups/{name}/restore` (job), `POST /host/rekey` (job) |
| #112 | `POST /login`, `POST /logout` (UI session only); reads `/whoami` and `/status` |
| #113 | `GET /backups/schedule`, `PUT /backups/schedule` |
| #114 | `GET`, `POST`, `PATCH`, `DELETE` on `/users/{id}/agents/{agent_id}/memory` |
| #115 | `GET /status` gains `engine.tool_calling` (result of the startup probe) |
| #116 | `GET`, `POST /mcp/servers`; `GET`, `PATCH`, `DELETE /mcp/servers/{id}`; `POST /mcp/servers/{id}/test`; `GET /mcp/servers/{id}/tools`; `PATCH /mcp/servers/{id}/tools/{tool}` |
| #117 | `GET`, `PUT /mcp/grants`; `GET /mcp/calls`; `POST /mcp/servers/{id}/approve-definitions` |
| #118 | `POST /mcp/sidecars`, `DELETE /mcp/sidecars/{name}` (host scope) |
| #119 | `GET`, `POST`, `PATCH`, `DELETE /skills`; `PUT /agents/{id}/skills` |
| #120 | inside `/routing` |
| #121 | `GET /agents/{id}/exposure` |
| #123 | `GET /telemetry?since=&until=&group_by=` |
| #124 | `GET /users/{id}/conversations/export?format=` |
| #125, #129, #130 | configuration keys through `/config` |
| #126 | `GET`, `PUT /retention`; `POST /retention/run` (job, `dry_run` flag) |
| #127 | `GET`, `POST /tasks`; `GET`, `PATCH`, `DELETE /tasks/{id}`; `POST /tasks/{id}/run`; `POST /tasks/pause` |
| #131 | `POST /backups/export` (job), `POST /backups/import` (job) |
| #122, #128, #132 | no new route |

Each issue keeps its "Admin UI" line; the contract tests of #109 fail when one of these routes
exists without a script command or a UI reach.

## 6. Gaps that remain, tracked

- Routes of section 5 do not exist yet: each is in its issue.
- The running container serves the API of before #108: rebuild by the owner (tracked in the #108
  status comment).
- The API has one identity, the key, until named administrators exist (deferred S1 to S3).
