"""Check that splitting CLAUDE.md into CLAUDE.md + docs/HISTORY.md (#71) lost
nothing: every top-level bullet of the old file must appear, whitespace
normalised, in one of the two new files, and every bullet of the old rules
block must appear in CLAUDE.md itself.

Usage: python3 scripts/check_claude_split.py OLD_CLAUDE.md OLD_RULES_FIRST_LINE OLD_RULES_LAST_LINE
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BULLET = re.compile(r"^(- |\d+\. )")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def bullets(lines: list[str], first: int = 1, last: int | None = None) -> list[str]:
    """Top-level bullets: a line starting `- ` or `N. `, plus the indented or
    blank-separated continuation lines that follow it, until the next
    unindented line that is not a bullet.
    """
    found: list[list[str]] = []
    open_bullet = False
    for number, line in enumerate(lines, start=1):
        if number < first or (last is not None and number > last):
            continue
        if BULLET.match(line):
            found.append([line])
            open_bullet = True
        elif line.strip() and line.startswith(" ") and open_bullet:
            found[-1].append(line)
        elif line.strip():
            open_bullet = False
    return [_norm(" ".join(b)) for b in found]


def main() -> int:
    old = Path(sys.argv[1]).read_text().split("\n")
    rules_first, rules_last = int(sys.argv[2]), int(sys.argv[3])
    new_claude = _norm((ROOT / "CLAUDE.md").read_text())
    history = _norm((ROOT / "docs" / "HISTORY.md").read_text())

    everything = bullets(old)
    in_either = [b for b in everything if b in new_claude or b in history]
    rules = bullets(old, rules_first, rules_last)
    rules_in_claude = [b for b in rules if b in new_claude]

    print(f"top-level bullets of the old file : {len(everything)}")
    print(f"  found in CLAUDE.md or HISTORY.md: {len(in_either)}/{len(everything)}")
    print(f"bullets of the old rules block    : {len(rules)}")
    print(f"  found in CLAUDE.md              : {len(rules_in_claude)}/{len(rules)}")
    for missing in [b for b in everything if b not in in_either][:5]:
        print("MISSING:", missing[:100])
    for missing in [b for b in rules if b not in rules_in_claude][:5]:
        print("RULE NOT IN CLAUDE.md:", missing[:100])
    ok = len(in_either) == len(everything) and len(rules_in_claude) == len(rules)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
