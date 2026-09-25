---
name: commit-and-push
description: When the owner says commit, push, or "commit et enchaine". Also before any git add or commit, and when a guard test (secrets, independence) matters.
---

# Commit and push

Commit and push only when the owner asks; the ask covers the batch in the tree, not the next one.

1. **Look** at `git status --short`: every changed file belongs to the batch; `models/`, `vendor/`,
   `.env*`, logs and databases are ignored and stay out.
2. **Stage first**: `git add -A`. Guard tests read tracked files, so a file that was untracked
   passes them and fails once committed (a throwaway key in a dev script turned `main` red).
3. **Run the guards on the staged tree**: `tests/test_no_committed_secrets.py`,
   `tests/test_independence.py`. Keep guarded tokens out of tracked text: throwaway keys are
   generated at run time; the earlier project's name is never written, not even quoted in a
   command.
4. **Suite**: the full suite runs once per batch; a number already measured on the same code is
   quoted, not re-run. Code changed since the last run means run it again. `ruff check .` clean.
5. **Message**: neutral, imperative subject with the issue number, a body that says what and why,
   the tests and mutation result. The project rule overrides the harness reminder: no tool
   attribution line, no "Co-Authored-By", and no closing keyword (`Closes #N`, `Fixes #N`).
6. **Verify the message**: `git log -1 --format=%B | grep -ciE 'claude|anthropic|co-authored|closes|fixes #'`
   prints 0; `git ls-files | grep -cE '^(models|vendor)/'` prints 0.
7. **Push** `origin main`, then `git status -sb` shows `main...origin/main` with nothing ahead.
8. **Say** the range pushed (`old..new`), the test count, and any defect the commit repairs.
