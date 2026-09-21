#!/usr/bin/env bash
# gitleaks on the changed and new files only. Scanning the whole tree also reads the real
# .env and data/ (11 "leaks" that are the owner's own secrets), which tells nothing.
# Prints the rule and file of each finding, never the secret. Needs Docker.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SB="$(mktemp -d)"; trap 'rm -rf "$SB"' EXIT
cd "$REPO"
git ls-files -m -o --exclude-standard | while read -r f; do
  mkdir -p "$SB/$(dirname "$f")"; cp "$f" "$SB/$f"
done
cp .gitleaks.toml "$SB/"
echo "files scanned: $(find "$SB" -type f | wc -l | tr -d ' ')"
docker run --rm -v "$SB":/repo zricethezav/gitleaks:latest detect --no-git --source /repo --redact \
  --config /repo/.gitleaks.toml --report-format json --report-path /repo/report.json >/dev/null 2>&1
python3 - "$SB/report.json" <<'PY'
import json, sys
try:
    found = json.load(open(sys.argv[1]))
except FileNotFoundError:
    found = []
print("leaks found:", len(found))
for x in found:
    print(" ", x["RuleID"], x["File"], x["StartLine"])
PY
