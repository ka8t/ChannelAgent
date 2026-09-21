"""Generic mutation checker: apply ONE deliberate defect at a time, run the
targeted tests, restore the file, print the result. A mutation that leaves the
tests green is a *survivor*: add a test for it, or document why it is equivalent.

Usage (from the repository root):

    .venv/bin/python scripts/dev/mutation_check.py SPEC.py

SPEC.py defines:
    TESTS      list of pytest arguments (files or node ids)
    MUTATIONS  {name: (file, old, new)}   `old` must occur in `file`; only its
               first occurrence is replaced (so give enough context to be unique)

Every mutation is checked to have applied (an `old` that is not found is an
error, not a pass), and the original text is restored in a `finally`, whatever
happens. The exit status is 1 when a mutation survived or could not be applied.
The specs in scripts/dev/mutations/ are examples of the older, self-contained
form of the same idea.
"""

import runpy
import subprocess
import sys
from pathlib import Path


def _run(tests: list[str]) -> str:
    result = subprocess.run(
        [".venv/bin/python", "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
    )
    lines = result.stdout.strip().splitlines()
    return lines[-1] if lines else "no output"


def main(spec_path: str) -> int:
    spec = runpy.run_path(spec_path)
    tests, mutations = spec["TESTS"], spec["MUTATIONS"]
    originals: dict[str, str] = {}
    problems = 0
    try:
        for name, (file, old, new) in mutations.items():
            path = Path(file)
            originals.setdefault(file, path.read_text())
            text = originals[file]
            if old not in text:
                print(f"{name} -> NOT APPLIED ('old' not found in {file})")
                problems += 1
                continue
            path.write_text(text.replace(old, new, 1))
            outcome = _run(tests)
            path.write_text(text)
            caught = "failed" in outcome or "error" in outcome
            if not caught:
                problems += 1
            print(f"{name} -> {outcome}{'' if caught else '   <-- SURVIVED'}")
    finally:
        for file, text in originals.items():
            Path(file).write_text(text)
    print(f"{len(mutations)} mutation(s), {problems} survivor(s) or not applied")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
