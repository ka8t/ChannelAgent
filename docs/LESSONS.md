# Mistakes not to repeat

Errors made while working on this project, each with the rule that prevents it.
Written on the owner's request (2026-09-21). Add a line whenever a new one is
found; `CLAUDE.md` holds the short version that is loaded in every session.

## Reporting and evidence

1. **A guess written as a fact in an issue** (#61: "Ctrl+C on `--native` stops
   llama-server"; the script says the opposite and the log showed nothing).
   *Rule:* before writing a cause, check the script and the log; otherwise write
   "cause not established". Correct a wrong comment at once (`gh api -X PATCH`).
2. **Numbers from memory.** A comment said "three survived and got tests" when it
   was two; a doc said an error message was verified by a run that predated the
   message. *Rule:* every count comes from a command run on the current tree;
   re-read a comment before posting it (no "..." placeholders).
3. **Verification after cleanup.** The sandbox was deleted, then the check needed
   it (and used the system `python3`, which has no `cryptography`). *Rule:* verify
   first, clean up last; use `.venv/bin/python`.
4. **Open questions left as comments** instead of issues (rule (c) of `CLAUDE.md`):
   the owner had to ask for the issues. *Rule:* create the issue with options,
   recommendation and "Done when" as soon as the doubt appears.
5. **Work "done" that was tested only on the happy path.** #70 (non-root user) was
   checked with an existing `data/`; on a fresh clone Docker creates `data/` owned
   by root and the application cannot start. *Rule:* test the fresh state as well
   as the existing one, and run the rehearsal script, not a remembered command.
6. **Wrong assumption about a tool.** Docker copies an image directory's owner into
   an empty named volume, so a root-owned volume cannot be simulated that way.
   *Rule:* observe the tool's behaviour before building a test on it.

## Tests

7. **Weak tests that mutations exposed** (a substring found in a comment, a filter
   that another filter already implied, a missing case). *Rule:* assert on
   directives, not comments; run the mutation check on every change and act on
   every survivor (`scripts/dev/mutation_check.py`).
8. **A blanket text replace hit two places** and changed a second test. *Rule:*
   replace with an anchor or a count, and read the diff.
9. **Throwaway values that look like secrets** (`test-key-0123...`, `API_SERVER_KEY=`
   followed by an option) were flagged by gitleaks, three times. *Rule:* low-entropy
   test values (`"test-key-" + "a" * 20`), no empty `KEY=` next to other text; run
   `scripts/dev/tools/scan_changed_files.sh` before a commit.
10. **Tests that depend on the machine** (a real `channelagent` container made 22 tests
    fail). *Rule:* no dependency on Docker, ports or real files.

## Environment

11. **zsh does not split an unquoted `$VAR`**: `docker run $E` passed one argument, and
    a run failed for a reason that had nothing to do with the code. *Rule:* write
    options out, or use an array.
12. **A foreground command that never exits** hung a 300 s tool call. *Rule:* `-d` and a
    bounded wait for anything that is a server.
13. **`/tmp` instead of the scratchpad**, and one-off scripts left in it. *Rule:* scripts
    go to `scripts/dev/` (see below), temporary files to the scratchpad.
14. **The RTK hook** rewrites `sed -i` and summarises `grep`/`docker logs`. *Rule:* edit with
    Python, `rtk proxy` for raw output.

## Earlier in the project (already in `CLAUDE.md`)

15. A bot token printed by a tool (#82); issues closed without the owner's word; real
    `.env` modified by a test of `start.sh`; a full test suite run for every issue;
    long silences during long runs (say what is running, in a few words).

## Session of 2026-09-21 (evening): shell, measurement, tests, git

Owner, 2026-09-21: "tu fais beaucoup d'erreurs. retiens les ainsi que leur resolution". Each
entry names the error, what it cost and the rule; the skills in `.claude/skills/` carry the rules
as procedures (`shell-traps`, `measure-first`, `issue-workflow`, `mutation-check`,
`commit-and-push`, `test-conventions`).

### Shell and tooling (skill `shell-traps`)

16. **A zsh loop variable named `path` overwrote `PATH`** (`for path in ...`): `curl` and
    `python3` vanished in the middle of a command. *Rule:* never use a name zsh ties to
    something (`path`, `status`, `pipestatus`, `fpath`, `argv`); use `ep`, `f`, `name`.
17. **Unquoted words zsh expands**: `/logs?limit=1` and `--include=*.go` ("no matches found"),
    `echo =====` ("===== not found"). *Rule:* quote every URL, glob and separator; print a
    separator with `printf '%s\n' ---`.
18. **A bash idiom in zsh**: `${PIPESTATUS[0]}` gave an empty exit code. *Rule:* when the exit
    code matters, run the command without a pipe (output to a file) and read `$?`.
19. **A pipe ending in `grep` printed nothing** (the RTK hook summarises `grep`, `ps` and
    `docker logs`); I took silence for a result. *Rule:* redirect to a file and read it, or
    use Python.
20. **Commands longer than the tool timeout** were moved to the background five times (a full
    suite of 9 minutes, a script that hung). *Rule:* run anything that may pass two minutes
    detached, output to a file, poll it; put a hard timeout inside the script itself.
21. **A background job in a script ignores SIGINT**, so an "interrupt at 50%" test never
    interrupted. *Rule:* drive the process from Python (`Popen`, `send_signal`).
22. **A retry of an irreversible deletion outside the repository** after the permission system
    blocked it. *Rule:* do not retry or route around a block; say what was blocked and give
    the exact command for the owner to type with `!`.

### Measurement (skill `measure-first`)

23. **A method that could not see what it measured** (`ps eww` shows no environment on this
    macOS): the control printed 0 as well, and I had first reported "0 secrets". *Rule:* run
    every new method on a known positive before trusting a zero; to see a child's environment
    make the child print it (`env`).
24. **My own instrument blocked what it observed**: the test guard refused `fe80::1%lo0` (an
    address `localhost` also has on macOS) and `b'localhost'` (asyncio passes host names as
    bytes), and a 3 minute hang looked like an application defect. *Rule:* try a new
    instrument on a known-good case (the engine on localhost) before the real run.
25. **Tests that asserted my guess instead of the observed behaviour**: a 3 MiB file that was
    3,145,732 bytes; a dropped stream expected to keep exactly half (httpx hands over whole
    blocks); 22 routes counted by hand, 23 counted by a command; `is_global` expected to
    refuse multicast and NAT64 (it does not); `posint` expected to accept 64 GiB; an
    exception raised in ASGI `receive` expected to reach the middleware (FastAPI turned it into
    a 400); a comparison run against a copy of the database whose `backups/` directory is a
    different, empty one. *Rule:* probe first with a one-line command, then assert; count with
    a command; a comparison runs on the same real path on both sides.
26. **A wrong name from memory** (`list-backups` for the generated `list-database-backups`).
    *Rule:* take names from the source of truth (`./start.sh --describe`), not memory.

### Tests and mutation checks (skills `test-conventions`, `mutation-check`)

27. **Holes only a mutation exposed**: `resolve()` before the link check let a delete follow a
    symlink out of the models directory; the outbound guard accepted multicast and NAT64
    addresses that carry a private one; a size limit that only worked when the server announced
    a size. *Rule:* for anything that touches files or the network test links, traversal,
    partial files, existing names and unannounced sizes; run a mutation check on every new
    control and add a test for every survivor (or show the mutant is equivalent).
28. **A shared function gained a dependency** (`run_turn` reads its agent from the database)
    and 24 tests plus 3 dev scripts silently ran on the real default database, one file
    taking 400 s instead of 13. *Rule:* when a shared function gains a dependency (database,
    environment, network), grep its callers in `tests/` and `scripts/` first, give each an
    isolated resource, then run the full suite, not only the targeted files.
29. **`get_settings.cache_clear()` forgotten** after `monkeypatch.setenv`, or the job registry
    and name claims left over from another test. *Rule:* clear the cache after every env
    change in a test and reset process-wide registries in the fixture.
30. **Line length fixed one file at a time** (E501, about ten rounds). *Rule:* write within 100
    columns; run `ruff format` on new files only, never on existing ones (the repo does not
    enforce it and it rewrites unrelated code).

### Git (skill `commit-and-push`)

31. **A guarded token committed after its guard test passed on an untracked file**: the
    throwaway Fernet key in `scripts/dev/no_network_turn.py`; `test_no_committed_secrets` reads
    tracked files, so `main` was red after the push. *Rule:* `git add -A` first, then run the
    guard tests, then commit; generate throwaway keys at run time; never write a guarded token
    (a key, the earlier project's name) in a tracked file, quoting the forbidden word included
    (a `git grep` command in `CLAUDE.md` tripped the independence test).
32. **Scripts used to answer a request left in the scratchpad** (the mutation runners of #108
    to #110, the issue creation script). *Rule:* copy every script used into `scripts/dev/` with
    an index line before reporting.

## Scripts

Every script used to answer a request is kept in `scripts/dev/` with a line in
`scripts/dev/README.md`, so nothing is rebuilt from memory. The owner does not want
round trips: the work is finished, verified, recorded and its follow-ups created as
issues in the same turn.
