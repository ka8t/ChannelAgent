---
name: mutation-check
description: After writing a new control, validation, guard or limit, or when a review asks whether a test really protects a rule. Use to break the rule on purpose, run the tests and act on every survivor.
---

# Mutation check

A mutation is one deliberate defect put in the code. The test suite is judged by whether it
notices. Nothing changes for good: the file is restored in a `finally`.

## Run
1. List one mutation per control: the check removed (`if False:`), a bound loosened, a step
   skipped, a value hard-coded, a flag flipped. Pattern of each: `(name, path, old, new)`.
2. For each: assert `old` is in the file (a silent miss looks like a caught mutant), write the
   mutated file, run the targeted tests, record the failing test names, restore the file.
   Reference runners: `scripts/dev/mutation_check.py SPEC` and `scripts/dev/mutations/*.py`.
3. After the loop run `git diff --stat` on the touched files and the tests once more.
   Criterion: the code is back to its real state and green.

## Read the result
- **Caught**: at least one test failed, and it is the test written for that control.
- **Survivor**: everything stayed green. Decide, in this order:
  1. The test is missing or too loose: add one that fails on the mutant, rerun that mutant.
     Typical: a check reached first by another check, an edge case (link, traversal, partial
     file, unannounced size, existing name).
  2. The mutant is equivalent (a second check makes the first redundant, or the library already
     refuses it): say so in the issue comment with the reason.
- Count "caught" only when the failing test is about that control.

## Where to look
Every new limit, allow-list, scope, validation, redaction, audit event, cleanup on failure,
default, and each branch of an error message a caller relies on.
