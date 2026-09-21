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

## Scripts

Every script used to answer a request is kept in `scripts/dev/` with a line in
`scripts/dev/README.md`, so nothing is rebuilt from memory. The owner does not want
round trips: the work is finished, verified, recorded and its follow-ups created as
issues in the same turn.
