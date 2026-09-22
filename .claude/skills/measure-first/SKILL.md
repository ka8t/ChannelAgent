---
name: measure-first
description: Before writing a number, a cause, "verified" or "0" in a report, an issue comment or a test assertion. Also before trusting a new measuring method, a count made by hand, or a test written from an assumption about a library or the OS.
---

# Measure first

The report holds only what a command showed on the current tree. Steps, each with its criterion:

1. **Try the method on a known positive.** The method sees something when the thing is there
   (`ps eww` printed nothing even for a variable I had just exported, so its "0" meant nothing).
   Criterion: a control that must give a non-zero gives it.
2. **Probe before asserting.** Run a one-line command to see the real behaviour, then write the
   assertion. Guesses that failed: a file size, "half" of a stream (httpx yields whole blocks),
   `is_global` on multicast and NAT64, the largest value `posint` accepts, where an exception
   raised in ASGI `receive` ends up. Criterion: every constant in a test comes from an observed
   value.
3. **Count with a command.** Routes, tests, issues, files: `wc`, `len`, a query. A count typed
   from memory was wrong (22 for 23 routes).
4. **Use a second, independent tool.** The code says the hash matches; `shasum` agrees. The API
   says the file is there; `ls` agrees. Criterion: the two figures are equal.
5. **Run on the real machine first**, on a consistent copy of the real data: the Mac, the live
   engine, `sqlite3 .backup`. Both sides of a comparison read the same real path.
6. **Measure after the last edit.** A figure taken before a change is stale. Criterion: the
   command ran after the last file was saved.
7. **Name what is not established.** "Cause not established" when unmeasured. Quote the exact
   figure and the command, never "it works".

Test the instrument itself when it can interfere with what it watches: a guard that refuses
"everything but loopback" first runs against the known-good engine on localhost.
