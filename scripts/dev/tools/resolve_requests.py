"""Approve or deny access requests of the REAL application through its Admin API (one writer:
the running app). Reads API_SERVER_KEY and the port from .env; the key is never printed.

Usage: .venv/bin/python scripts/dev/tools/resolve_requests.py approve:1 deny:2 deny:3
       .venv/bin/python scripts/dev/tools/resolve_requests.py list
"""
import json
import sys
import urllib.error
import urllib.request

env = dict(
    line.split("=", 1)
    for line in open(".env").read().splitlines()
    if "=" in line and not line.startswith("#")
)
base = f"http://127.0.0.1:{env.get('API_SERVER_PORT', '8700')}"
key = env["API_SERVER_KEY"].strip("'\"")


def call(method, path):
    request = urllib.request.Request(base + path, method=method, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:200]


for arg in sys.argv[1:] or ["list"]:
    if arg == "list":
        status, rows = call("GET", "/requests?status=all")
        print("HTTP", status, [(r["id"], r["channel"], r["status"], r["resolved_by"]) for r in rows])
        continue
    action, request_id = arg.split(":")
    status, body = call("POST", f"/requests/{request_id}/{action}")
    print(f"{action} {request_id}: HTTP {status}")
