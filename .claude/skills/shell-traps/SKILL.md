---
name: shell-traps
description: Shell on this Mac (zsh, RTK hook, tool timeout). Use before writing a loop, a URL or glob, a pipe whose exit code matters, a check of a process's environment, a command that may pass two minutes, or a delete outside the repository.
---

# Shell traps on this Mac

Each rule is an incident of 2026-09-21 (`docs/LESSONS.md` 16 to 22). A command is ready to run
when every item below that applies to it is satisfied.

## Names
- Name loop variables `ep`, `f`, `name`. zsh ties `path` to `PATH`, and `status`, `pipestatus`,
  `fpath`, `argv` to shell state: assigning one breaks the shell (`curl` vanished mid-command).
- Write options out or use an array; zsh does not split an unquoted `$VAR`.

## Quoting
- Quote every URL, glob, pattern and separator: `'/logs?limit=1'`, `--include='*.go'`.
- Print a separator with `printf '%s\n' ---`; `echo =====` fails in zsh.

## Exit codes
- Read `$?` from a command run without a pipe (output to a file first). `${PIPESTATUS[0]}` is
  bash; zsh gives an empty string.

## Output
- Redirect to a file and read the file. The RTK hook summarises `grep`, `ps`, `docker logs`, so a
  pipe ending in one of them can print nothing.
- Edit files with Python and `assert old in text` (the hook breaks `sed -i`); use `rtk proxy
  <cmd>` for raw output.

## Processes
- Make a child print its own environment (`env`) to see what it inherited. `ps eww` shows no
  environment on this macOS, even for a known variable.
- Drive an interrupt test from Python: `Popen`, then `send_signal(SIGINT)`. A background job in a
  script ignores SIGINT.
- `localhost` resolves to `127.0.0.1`, `::1` and `fe80::1%lo0`; asyncio hands host names over as
  `bytes`. A guard that refuses "everything but loopback" has to accept all of these.

## Duration
- Run a command that may pass two minutes detached (`nohup ... > file 2>&1 &`), poll the file, and
  put a hard timeout inside the script (`asyncio.wait_for`). Say in one line what is running.

## Blocked actions
- A permission block on an irreversible action outside the repository ends the attempt: state
  what was blocked and give the exact command for the owner to type with `!`.
