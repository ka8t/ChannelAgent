---
name: issue-workflow
description: Implementing or verifying a GitHub issue of this project (ka8t/ChannelAgent). Use when the owner says implement, continue, chain, verify the issues, or when a report or issue comment is due.
---

# One issue, start to finish

The owner's method (2026-09-21): "tu implemente, tu testes, tu valides, et me donne les
resultats". The issue is done when every step below meets its criterion. Priorities run P0 to
P3 in the owner's order; the P1 order is in the epic #106 comment.

1. **Read** the issue body and every comment. Criterion: each Scope bullet and each Done-when
   line is written down as a check, plus the constraints (English only, no other repository,
   secure by design, `start.sh` and the UI as clients of the API).
2. **Implement** in the layer that owns it (service, API, script client from the same routes).
   Criterion: an unsafe input is refused with a stable message, a job for anything long, an
   admin event for a change, a new route has a scope, a tag and documented errors.
3. **Test** the touched files. Skills `test-conventions` and `measure-first` apply.
4. **Mutation-check** every new control (skill `mutation-check`). Criterion: no survivor left
   that is not shown to be equivalent.
5. **Validate on the real machine** (skill `measure-first`, step 5): the real engine, a copy of
   the real database, the real hub. Criterion: each Done-when figure measured and quoted.
6. **Full suite once**, and after any change to shared code. Callers of a function that gained a
   dependency (database, env, network) in `tests/` and `scripts/` are grepped first.
7. **Record**: a status comment on the issue with the exact figures, the defects found on the
   way, what is not delivered and where it is tracked; docs updated in the same change
   (`docs/ARCHITECTURE.md`, README); every script used copied to `scripts/dev/` with an index
   line; the session written into `docs/HISTORY.md`.
8. **Report** in French: results, defects found, what remains, next issue. No questions in chat:
   a doubt becomes an "Open question(s)" comment with options, a recommendation and a Done-when.

## Limits
- The issue stays open: closing is the owner's decision, even with all checks green.
- New issues only when the owner asks (sub-issues on request); a limit accepted or a gap goes in
  the status comment.
- Commit and push only on the owner's word (skill `commit-and-push`).
- Verification of finished issues compares the whole scope with the code, then re-runs each
  Done-when against the current tree and the live container
  (`scripts/dev/tools/verify_session_issues.py`).
