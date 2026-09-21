"""Creates the follow-up issues for the open points left in the status comments of
2026-09-21 (#47, #48, #60, #64, #65, #70, #77, #78). Kept as the record of what was
created and as a template: each issue has options, a recommendation and "Done when".
Run once (it does not check for duplicates):  python3 scripts/dev/tools/create_followup_issues_2026-09-21.py
"""

import subprocess

REPO = "ka8t/ChannelAgent"

ISSUES = [
    ("Summarize the dropped turns of a long conversation instead of forgetting them", ["P3-low", "question", "area:langgraph"],
     "Follow-up of #47. The history sent to the model is windowed (75% of `LLAMA_CTX_SIZE`); turns outside the window are forgotten by the model.\n\n"
     "## Options\n(a) keep the window only (current); (b) summarize the dropped part with one extra model call when the window first overflows, and prepend it.\n\n"
     "## Recommendation\n(a) now. (b) only if a real conversation shows the loss matters: it adds a call, latency and a failure mode on every long thread.\n\n"
     "## Done when\nThe owner picks. For (b): a test shows the summary in the request and the request under the budget (numbers quoted)."),
    ("Count tokens exactly with llama-server /tokenize instead of estimating", ["P3-low", "question", "area:langgraph"],
     "Follow-up of #47. The window uses about 4 characters per token; the 25% margin absorbs the error.\n\n"
     "## Options\n(a) keep the estimate; (b) ask `llama-server` `/tokenize` for exact counts.\n\n"
     "## Recommendation\n(a) until one request is rejected for length.\n\n"
     "## Done when\nOne measured rejection (then implement (b) with a test), or the owner asks."),
    ("A single message larger than the context window still fails", ["P3-low", "question", "area:channels"],
     "Follow-up of #47. A message alone above the window is sent whole and fails; it is recorded as a failed turn with the apology (#51).\n\n"
     "## Options\n(a) leave; (b) refuse it up front with a clear reply and an audit entry.\n\n"
     "## Recommendation\n(a): the failure path already answers.\n\n"
     "## Done when\nThe owner picks; for (b) a test with a message above the window shows the reply and 0 model calls."),
    ("Nothing restarts a container that turns unhealthy", ["P3-low", "question", "area:docker"],
     "Follow-up of #48. `restart: unless-stopped` reacts to an exit, not to Docker's health status; `unhealthy` is only reported.\n\n"
     "## Options\n(a) leave, watch `docker compose ps`; (b) an `autoheal`-style sidecar that restarts unhealthy containers; (c) an external monitor.\n\n"
     "## Recommendation\n(a) on a single host (#83 already exits when every component died); (b) if the VPS runs unattended.\n\n"
     "## Done when\nThe owner picks; for (b) a throwaway container frozen with SIGSTOP is restarted (quoted)."),
    ("A component stuck on the network still reads healthy", ["P3-low", "question", "area:docker", "area:channels"],
     "Follow-up of #48. The healthcheck proves the process and its event loop are alive, not that Telegram or the mailbox answer.\n\n"
     "## Options\n(a) leave; (b) each adapter records its last successful poll and the heartbeat depends on it.\n\n"
     "## Recommendation\n(a) until one stuck adapter is observed (the adapters already log poll failures).\n\n"
     "## Done when\nOne observed stuck adapter, or the owner asks; then a test with a stalled fake adapter turns the container unhealthy (quoted)."),
    ("SSH tunnel recipe for the Admin API is documented but not tested", ["P3-low", "question", "area:security"],
     "Follow-up of #60. `ssh -L 8700:127.0.0.1:8700 <host>` is in the docs; no SSH server runs on the development Mac.\n\n"
     "## Options\n(a) test on the VPS when there is one; (b) test now against a throwaway `sshd` container.\n\n"
     "## Recommendation\n(a), unless the owner wants it verified before a VPS exists.\n\n"
     "## Done when\n`curl http://127.0.0.1:<local port>/users` through the tunnel gives 401 without a key and 200 with (quoted)."),
    ("TLS proxy with a public name and an automatic certificate is untested", ["P3-low", "question", "area:security"],
     "Follow-up of #60. `docker-compose.tls.yml` is tested with `tls internal`; Caddy's default (ACME, ports 80 and 443) needs a real DNS name and a reachable host.\n\n"
     "## Recommendation\nTest it together with the VPS.\n\n"
     "## Done when\n`curl https://<name>/users` gives 401 and 200 with a publicly trusted certificate (quoted)."),
    ("A failed turn that is retried appends its user message to the history again", ["P2-medium", "bug", "area:langgraph"],
     "Follow-up of #64. A failed turn leaves its user message in the checkpoint; the email retry runs the turn again and appends the same message a second time. Observed: history of 3 messages after fail-then-retry instead of 2.\n\n"
     "## Options\n(a) leave (one repeated line); (b) on a retried turn, do not append the user message when the last stored message is identical.\n\n"
     "## Recommendation\n(b).\n\n"
     "## Done when\nA test shows 2 messages in the history after fail-then-retry (quoted), and `pytest`: N passed, 0 failed."),
    ("Two messages with the same text from the same sender can be mistaken for one another", ["P3-low", "question", "area:channels"],
     "Follow-up of #64. The undelivered-answer lookup pairs an inbound entry with the next outbound entry by exact text.\n\n"
     "## Recommendation\nAccept: same sender, same text, near-identical answers.\n\n"
     "## Done when\nThe owner picks."),
    ("Resolve the two pending access requests of the real database", ["P3-low", "question", "area:admin-cli"],
     "Follow-up of #65 (owner action on real data, so not done by the assistant). Request 1 (`montezuma@outlook.fr`, stale) and request 2 (an automated website alert taken before the tag rule) are still pending.\n\n"
     "## Recommendation\nApprove 1 and deny 2 from `./start.sh --admin`, menu 1.\n\n"
     "## Done when\n`GET /requests` returns `[]` (quoted)."),
    ("The CI step asserting the container uid cannot run while CI is disabled", ["P3-low", "question", "area:tooling"],
     "Follow-up of #70. `ci.yml` asserts `id -u` is 10001; CI is disabled at the owner's request, so no run id exists. The same check runs locally (`scripts/dev/rehearsals/container_user.sh`).\n\n"
     "## Options\n(a) accept the local evidence; (b) re-enable CI once (`gh workflow enable 361230655`) and quote the run id.\n\n"
     "## Done when\nThe owner picks; for (b) the run id and the step's result are quoted."),
    ("Run the non-root container on a real Linux Docker Engine bind mount", ["P3-low", "question", "area:docker"],
     "Follow-up of #70. Verified on Docker Desktop and with a `tmpfs` stand-in for a root-owned directory; a real Linux bind mount was not run. Documented step: `sudo chown -R 10001:10001 data`.\n\n"
     "## Recommendation\nConfirm on the VPS when there is one.\n\n"
     "## Done when\nOn a Linux host the application starts from a `data/` chowned as documented, `healthy` (quoted)."),
    ("Rebuild the running container so it runs as uid 10001 (owner action)", ["P3-low", "question", "area:docker"],
     "Follow-up of #70. The owner's `channelagent-channelagent-1` is still the old image (root). The new image was verified on a copy of the real data, not on the live one.\n\n"
     "## Recommendation\n`docker compose up -d --build` when convenient (`./start.sh` creates `data/` first).\n\n"
     "## Done when\n`docker exec channelagent-channelagent-1 id -u` prints 10001 and the container is `healthy` (quoted)."),
    ("start.sh --status and --stop do not see a hand-started app or another Compose project", ["P3-low", "question", "area:tooling"],
     "Follow-up of #77. A native application started by hand (`python -m app.main`) has no pid file; a container started by another Compose project name is not seen.\n\n"
     "## Recommendation\nAccept: the documented ways to start are the `start.sh` modes.\n\n"
     "## Done when\nThe owner picks."),
    ("Decide whether the old key may stay in .env.pre-rekey after a guided rotation", ["P3-low", "question", "area:security"],
     "Follow-up of #78. The \"Done when\" said the old key appears in no file; the tool keeps it in `.env.pre-rekey` (mode 600) because the `*-prerekey-*` database copies are unreadable without it. Measured: the old key is in no other file and no output.\n\n"
     "## Options\n(a) keep `.env.pre-rekey` (current); (b) do not write it and require the owner to have stored the old key elsewhere.\n\n"
     "## Recommendation\n(a).\n\n"
     "## Done when\nThe owner picks."),
    ("Owner cleanup: delete .env.pre-rekey and the prerekey copies once the new key is stored", ["P3-low", "question", "area:security"],
     "Follow-up of #67 and #78 (owner action). `./start.sh --rekey` refuses to run while `.env.pre-rekey` exists, and the leftover of the 2026-09-20 rotation is still there with `data/backups/channelagent-prerekey-*.db` and `checkpoints-prerekey-*.db`.\n\n"
     "## Recommendation\nStore the new `ENCRYPTION_KEY` (from `.env`) in a password manager, confirm the application runs, then delete those files.\n\n"
     "## Done when\n`ls .env.pre-rekey` fails and `ls data/backups | grep prerekey` prints nothing (quoted)."),
    ("Guided key rotation has no automatic resume after a partial failure", ["P3-low", "question", "area:security"],
     "Follow-up of #78. If the rotation fails after part of the data moved, both keys are kept and the message says how to finish by hand (`OLD_ENCRYPTION_KEY` from `.env.pre-rekey`, `python -m app.admin.rekey`).\n\n"
     "## Recommendation\nAccept: it needs two databases to fail independently after a verified plan.\n\n"
     "## Done when\nThe owner picks."),
]

for title, labels, body in ISSUES:
    cmd = ["gh", "issue", "create", "--repo", REPO, "--title", title, "--body", body]
    for label in labels:
        cmd += ["--label", label]
    print(subprocess.run(cmd, capture_output=True, text=True).stdout.strip())
