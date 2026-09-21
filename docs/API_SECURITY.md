# Admin API security design (proposal, 2026-09-21)

Owner: "l'API doit etre securisee by design". Status: design proposal for epic #106, nothing
here is implemented yet except what section 1 lists as existing. Decisions still open are in
"Open decisions" and in the epic's "Open question(s)" comment.

## 1. Why this needs a design and not a patch

Today (measured on the current tree: `app/api/app.py`, `app/api/deps.py`,
`docs/ARCHITECTURE.md` "Admin API exposure"):

- Already in place: one authentication dependency attached to the whole application (a route added
  later cannot ship unguarded), constant-time key comparison, key strength rules, a failed-attempt
  limiter (10 failures per address per 60 s, then 429), loopback binding by default, `/docs` and
  `/openapi.json` behind the key, a tested TLS proxy recipe, secrets redacted from logs (#82),
  admin actions recorded (#59).
- Accepted limits, documented: one shared key, not one per administrator (actor is `api`);
  behind Docker's gateway or a proxy every client shares one address, so the limiter can lock the
  administrator out; a valid key gives **every** right, including reading decrypted conversations.

The epic changes the stakes. The API becomes the only entry point and grows configuration write,
backup restore, key rotation, model download, and a host scope that starts and stops processes.
**Whoever controls this API controls everything**, so "one key, all rights" is no longer
acceptable. The UI adds a browser to the picture: cookies, cross-site requests, and text written
by channel users (untrusted) displayed to the administrator.

## 2. Assets, actors, boundaries

Assets, most sensitive first:

1. `ENCRYPTION_KEY` and the secrets in `.env` (bot token, mailbox password, API keys).
2. Decrypted conversation text and user identities.
3. The database and its backups.
4. The ability to run host operations (stop, restore, rekey, start, files under `models/`).
5. Model files and the engine.

Actors: the owner administrator; other administrators (later); a channel user (Telegram, email:
untrusted, can put arbitrary text in front of the administrator and the model); a local user of
the host machine; a malicious web page open in the administrator's browser; a network attacker
between an administrator and the service; a compromised dependency.

Trust boundaries: browser to UI/API; CLI to API; application container to the host helper; the
application to the engine; the application to the outside (model hub, later web fetch).

## 3. Principles

1. **Default deny, fail closed.** A route with no declared permission does not start (test at
   startup). Unknown route, unknown scope, missing configuration: refuse.
2. **Least privilege per operation**, not per key. Every route declares the scope it needs.
3. **Secure defaults.** Loopback only, host helper off, remote exposure off, arbitrary download
   hosts off, until an administrator turns each on explicitly.
4. **No secret ever leaves.** Not in a response, a log, an error, a URL, a job status.
5. **Everything sensitive is attributable.** Who (named account or `cli`), from where, what,
   result; appended to the audit trail.
6. **Defense in depth.** Authentication, authorization, input validation, output encoding,
   rate limits, network position, audit: each assumed to fail once.
7. **Verified, not claimed.** Every control has a test that fails when it is removed (mutation
   check, as for the rest of the project).

## 4. Controls

### 4.1 Authorization: scopes on every route
Four scopes, each includes the previous:
- `read`: status, lists, counts. No conversation text, no secrets.
- `operate`: users, access requests, agents, tasks, conversation reset.
- `admin`: configuration write (never secrets in clear), models, backups create and list, logs
  and conversation text (`read:content`, separately grantable and always audited).
- `owner`: restore, rekey, secret changes, host scope (start, stop, restart), token and account
  management, purge.
The route metadata already planned for the manifest (needs the application stopped, destructive,
host scope) gains `scope`. One dependency enforces it. **Authorization matrix test generated from
OpenAPI**: for every route and every scope, the expected status (200 or 403) is asserted; a new
route without a row fails.

### 4.2 Authentication
- **Named administrator accounts** (D10). Passwords hashed with a memory-hard function
  (`hashlib.scrypt`, stdlib, no new dependency: the dependency lock #69 stays small); minimum
  length and a breached-list check against a small local list; no default account: the first owner
  is created by `start.sh` at first run.
- **Tokens for clients** (script, helper calls, automation): random 256-bit tokens, only their
  hash is stored, each bound to an account and a scope, with expiry, last use, and revocation.
  The static `API_SERVER_KEY` stays valid only until the first named owner exists, then is
  refused (migration path for the live installation), and disappears from the documented flow.
- **Browser sessions** (UI): server-side session, cookie `__Host-` prefix, `HttpOnly`, `Secure`,
  `SameSite=Strict`; id rotated at login; idle timeout 30 minutes, absolute 8 hours; logout
  destroys it server side.
- **Step-up authentication** for destructive operations (restore, rekey, secret change, purge,
  token creation, conversation export): the password (and the second factor once enabled) is asked
  again if the last confirmation is older than 5 minutes. A stolen session cannot do the worst
  things silently.
- **Second factor** (TOTP, RFC 6238, stdlib implementable): required for `owner` scope
  (open decision S2).
- **Brute-force limits keyed on the account and the token, and on the address** with forwarded
  headers trusted only from a configured proxy list (`TRUSTED_PROXIES`), which removes the
  documented lockout-through-the-gateway weakness.

### 4.3 Transport and exposure
- Loopback or Unix socket by default. The application **refuses to start on a non-loopback
  address unless `API_REMOTE=tls-proxy` is set explicitly** (S5); with it, the strict transport
  header is sent. The reference proxy (#60) stays the documented path.
- **Host header allow-list** (`ALLOWED_HOSTS`) and, for state-changing requests, an `Origin`
  check: a web page cannot reach a loopback API through DNS rebinding.
- No CORS headers at all (same origin only).

### 4.4 Web layer (UI)
- CSRF token on every state-changing form, plus `SameSite=Strict`.
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-...'; frame-ancestors
  'none'; base-uri 'none'; form-action 'self'`, no inline script, no third-party origin
  (consistent with the no-CDN rule); `X-Content-Type-Options: nosniff`, `Referrer-Policy:
  no-referrer`, `Cache-Control: no-store` on every authenticated response.
- **Text from channel users is rendered as text, never as markup.** Autoescaping on, no `|safe`,
  no Markdown-to-HTML of conversation text. This is stored cross-site scripting waiting to happen
  otherwise: any Telegram user can write what the administrator will read.
- Test: a message containing a script tag and an event-handler attribute is stored, displayed in
  the log and conversation screens, and the page contains it only as escaped text.

### 4.5 Input validation and injection
- Every request body is a strict schema (`extra="forbid"`, bounded lengths, typed enums); body
  size limit (default 1 MB, larger only on declared upload routes); request timeout; cap on
  concurrent jobs.
- **No shell anywhere.** Host operations use argument lists, never `shell=True`, never string
  interpolation; parameters are matched against allow-lists (model file names
  `^[A-Za-z0-9._-]+\.gguf$`, paths resolved and checked to stay under the target directory).
- **Outbound requests are an attack surface** (SSRF): the model pull (#104) and the page fetch
  (A8) go through one guard: `https` only, allow-listed hosts (default: the model hub only),
  DNS resolved once and the address checked against private, loopback and link-local ranges, the
  same check on every redirect, size and time caps.

### 4.6 Secrets handling by the API
- Configuration read masks every secret; configuration write of a secret is write-only.
- `ENCRYPTION_KEY` is never readable and never settable through the generic configuration route:
  only the rekey job (#78) changes it, with re-encryption.
- Errors return a short stable message and an error id; details go to the log, redacted (#82).
  No stack trace, no SQL, no path in a response.
- Request and response bodies are never logged; the access log keeps method, route pattern,
  status, actor, duration.

### 4.7 The host helper (highest risk)
- Serves only the host-scope routes of the same API; a fixed table of operations, typed
  arguments, argument lists, no shell.
- Not reachable from the network: loopback only, or a Unix socket with mode 600 where the
  platform allows it. Docker Desktop on the Mac does not share host Unix sockets with containers
  and Linux Docker Engine does not reach a host loopback port from a container the same way, so
  the transport is decided per platform and tested on both (residual note in section 7).
- **Every call is signed**: HMAC over method, route, body hash, timestamp and a nonce with a
  secret shared with the application only (kept in `.env`, mode 600); calls older than 30 seconds
  or with a used nonce are refused (no replay). A leaked request cannot be repeated.
- The application forwards a host call only after its own authorization (`owner`, step-up done).
  The helper re-checks the scope claim in the signed payload and refuses anything not in its
  table.
- Off by default; started only by `start.sh` when enabled. Each call is an audit event before it
  runs and again with the result; a destructive call also raises an admin notification (#53).

### 4.8 Audit and detection
- Every mutating call, every read of conversation text, every authentication failure, every
  scope refusal, every host call, every token or account change: one event with actor (account,
  or `cli` plus the OS user), source, scope, route, result.
- **Tamper evidence**: each event stores the hash of the previous one; `./start.sh --audit verify`
  reports the first broken link. Deleting or editing an event is detectable (S4).
- Admin notification on: lockout, repeated failures, new token, host operation, restore, rekey.

### 4.9 Availability
Global per-identity rate limit, body and time limits, bounded job queue, bounded page size on
every list route (no unbounded query), bounded search cost (#56 measurements stay the reference).

### 4.10 In-process mode (application stopped)
The script calls the same handlers without a server. The boundary here is the operating-system
user who can read `.env` and the database (#68): that person is the owner by definition, and the
call still goes through the same authorization layer with actor `cli`. This is stated as a
residual risk, not hidden.

## 5. Test plan (security suite, part of the full run)

| Control | Test that fails when the control is removed |
|---|---|
| Default deny | startup refuses a route with no declared scope |
| Scopes | authorization matrix generated from OpenAPI: routes x scopes, expected 200 or 403 |
| Sessions | cookie flags, rotation at login, idle and absolute timeout, logout |
| CSRF and Origin | forged cross-site POST returns 403; wrong `Origin` returns 403 |
| Host header | request with a foreign `Host` returns 421 or 400 |
| Headers | CSP, nosniff, no-store, frame-ancestors present on every authenticated response |
| Stored XSS | script payload from a channel message appears only escaped in every screen |
| Brute force | 6th wrong login in a minute returns 429; other accounts unaffected |
| Step-up | destructive call after 6 minutes without confirmation returns 401 with a step-up code |
| Secrets | responses, errors, logs and job status contain no secret (extends the #82 test) |
| SSRF | pull or fetch of a private address, a redirect to one, a non-https URL: refused |
| Host helper | replayed request refused; unsigned refused; operation outside the table refused |
| Audit chain | editing one event makes `--audit verify` report it |
| Injection | shell metacharacters and `../` in every path and name parameter refused |

Each control also gets a mutation check: disable it, see exactly its test fail.

## 6. Open decisions (also in the epic)

**Deferred by the owner on 2026-09-21: S1 to S5 are handled later.** They stay here, with their
recommendations, for a future implementation. Until then the UI signs in with the existing admin
key (D10 option a) through a server-side session; sections 4.1 (scopes, default deny), 4.3 to 4.7
and 4.9 to 4.10 are not deferred.

- **S1, password hashing.** `hashlib.scrypt` (stdlib, no dependency) or `argon2-cffi` (one more
  locked dependency). Recommendation: scrypt.
- **S2, second factor.** Options: none; TOTP optional; TOTP required for `owner`. Recommendation:
  required for `owner` scope, optional below.
- **S3, tokens.** Hashed per-client tokens with scopes and expiry (recommended), or keep one static
  key. Recommendation: tokens; the static key works only until the first named owner exists.
- **S4, tamper-evident audit chain.** Recommendation: yes.
- **S5, remote exposure.** Refuse a non-loopback bind unless explicitly set to `tls-proxy`.
  Recommendation: yes.

## 7. Residual risks (accepted, stated)

- The operating-system user who owns the project directory is the owner: `.env`, the database
  and the helper secret are readable by that user (#68 keeps everyone else out).
- The container and the host share the helper secret; compromising the application container
  lets an attacker call the helper with the allowed table, each call audited, destructive ones
  needing a fresh step-up that the attacker does not have.
- Docker's shared gateway address keeps the per-address limiter coarse; the account and token
  limiters are the real protection.
- A compromised dependency is limited only by version pinning (#69) and the container boundary;
  there is no further process isolation. Out of scope here.

## 8. Where it lands in the plan

- P1, inside the issue "the API as single entry point": scopes on every route, default deny,
  authorization matrix test, secrets masking, error format, body limits, Host and Origin checks,
  no shell, access log without bodies.
- Deferred (owner, S1 to S5): the issue "named administrators, scoped tokens, sessions,
  step-up" (D10, S1, S2, S3), the audit chain (S4) and the remote-exposure refusal (S5).
- P1, the host helper issue carries section 4.7 as its requirements.
- P1, the UI foundation carries 4.4 (CSRF, CSP, escaping, cookies).
- P1, with #104: the outbound guard of 4.5 (model pull from a URL is an SSRF vector from day one);
  the page fetch (A8, P2) reuses it.
- P2: audit chain (S4), TOTP (S2).
