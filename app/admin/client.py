"""Command-line client of the Admin API (#109): one command, one API call.

    python -m app.admin.client describe [--json]
    python -m app.admin.client <command> [--flag value ...] [--json]
        [--transport auto|http|inprocess]

The commands, their flags and their help are generated from the API's own routes
(`app/admin/manifest.py`), so a new route is a new command with no client code, and the
script and the UI cannot behave differently: both call the same handlers. `./start.sh
--api <command> ...` and `./start.sh --describe` run this in the virtualenv.

Transports: `http` talks to the running application; `inprocess` calls the same handlers
without a server, for when the application is stopped; `auto` (default) picks `http` when
something listens on the API port. A route that starts a job (202) is waited for, and
`--no-wait` prints the job instead (an in-process job cannot outlive the command, so it
is always waited for).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import re
import socket
import sys
from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx

FINAL_JOB = {"done", "failed", "cancelled"}
POLL_SECONDS = 0.3


class UsageError(Exception):
    pass


def client_label() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001 - no login name in some containers
        user = "unknown"
    return "cli:" + (re.sub(r"[^A-Za-z0-9._-]", "_", user)[:32] or "unknown")


def _endpoint() -> tuple[str, int]:
    host = os.environ.get("API_SERVER_HOST", "127.0.0.1")
    if host in ("0.0.0.0", ""):
        host = "127.0.0.1"
    return host, int(os.environ.get("API_SERVER_PORT", "8700"))


def _is_up(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


@asynccontextmanager
async def open_client(transport: str):
    key = os.environ.get("API_SERVER_KEY")
    if not key:
        raise UsageError(
            "API_SERVER_KEY is not set (put it in .env, ./start.sh --set API_SERVER_KEY=...)"
        )
    headers = {"Authorization": f"Bearer {key}", "X-Client": client_label()}
    host, port = _endpoint()
    if transport == "auto":
        transport = "http" if _is_up(host, port) else "inprocess"
    if transport == "http":
        async with httpx.AsyncClient(
            base_url=f"http://{host}:{port}", headers=headers, timeout=120
        ) as client:
            client.transport_name = "http"  # type: ignore[attr-defined]
            yield client
        return
    from app.db.session import init_db
    from app.logging_setup import install_redaction
    from app.security.permissions import harden_process

    install_redaction()
    harden_process()
    await init_db()
    from app.api.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers=headers,
        timeout=120,
    ) as client:
        client.transport_name = "inprocess"  # type: ignore[attr-defined]
        try:
            yield client
        finally:
            graph = sys.modules.get("app.graph")
            if graph is not None:
                await graph.close_graph()


# --- the parser, generated from the manifest ---


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def _dest(name: str) -> str:
    return "field__" + name


def build_parser(operations: list[dict]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start.sh --api",
        description="Command-line client of the Admin API. `describe` lists the commands.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="print the response body as JSON")
    common.add_argument(
        "--transport",
        choices=["auto", "http", "inprocess"],
        default="auto",
        help="how to reach the API",
    )
    common.add_argument(
        "--no-wait", action="store_true", help="print a started job instead of waiting"
    )
    sub.add_parser("describe", parents=[common], help="list every command")
    for op in operations:
        p = sub.add_parser(
            op["command"],
            parents=[common],
            help=op["description"],
            description=f"{op['description']}  [{op['method']} {op['path']}, scope {op['scope']}]",
        )
        for f in op["fields"]:
            default = f" (default {f['default']})" if f["default"] is not None else ""
            p.add_argument(
                _flag(f["name"]),
                dest=_dest(f["name"]),
                required=f["required"] and f["default"] is None,
                choices=f["enum"],
                metavar=f["type"].upper(),
                help=(f["description"] or f["in"]) + default,
            )
    return parser


def _convert(field: dict, raw: str):
    kind = field["type"]
    try:
        if kind == "integer":
            return int(raw)
        if kind == "number":
            return float(raw)
        if kind == "boolean":
            if raw.lower() in ("true", "1", "yes"):
                return True
            if raw.lower() in ("false", "0", "no"):
                return False
            raise ValueError
        if kind in ("array", "object"):
            return json.loads(raw)
    except ValueError:
        raise UsageError(f"{_flag(field['name'])}: {raw!r} is not a valid {kind}") from None
    return raw


def request_parts(op: dict, args: argparse.Namespace) -> tuple[str, dict, dict | None]:
    path, query, body = op["path"], {}, {}
    for f in op["fields"]:
        raw = getattr(args, _dest(f["name"]), None)
        if raw is None:
            continue
        value = _convert(f, raw)
        if f["in"] == "path":
            path = path.replace("{" + f["name"] + "}", quote(str(value), safe=""))
        elif f["in"] == "query":
            query[f["name"]] = value
        else:
            body[f["name"]] = value
    has_body = any(f["in"] == "body" for f in op["fields"])
    return path, query, (body if has_body else None)


# --- calling and printing ---


async def wait_for_job(client: httpx.AsyncClient, job: dict) -> dict:
    while job["status"] not in FINAL_JOB:
        await asyncio.sleep(POLL_SECONDS)
        response = await client.get(f"/jobs/{job['id']}")
        response.raise_for_status()
        job = response.json()
    return job


def _cell(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 60 else text[:57] + "..."


def render(body) -> str:
    if body is None:
        return "ok"
    if isinstance(body, list):
        if not body:
            return "(none)"
        if all(isinstance(r, dict) for r in body):
            columns = list(body[0])
            rows = [
                [_cell(r[c]) if r.get(c) is not None else "" for c in columns] for r in body
            ]
            widths = [max(len(c), *(len(r[i]) for r in rows)) for i, c in enumerate(columns)]
            lines = ["  ".join(c.ljust(w) for c, w in zip(columns, widths, strict=True))]
            lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths, strict=True)) for r in rows]
            return "\n".join(lines)
        return "\n".join(_cell(item) for item in body)
    if isinstance(body, dict):
        return "\n".join(f"{k}: {_cell(v)}" for k, v in body.items())
    return str(body)


def _dump(body, as_json: bool) -> str:
    return json.dumps(body, indent=2, ensure_ascii=False) if as_json else render(body)


async def execute(client: httpx.AsyncClient, op: dict, args: argparse.Namespace):
    """One API call, then the job it started if any. Returns (status code, body)."""
    path, query, body = request_parts(op, args)
    response = await client.request(op["method"], path, params=query or None, json=body)
    if response.status_code == 204:
        return 204, None
    try:
        payload = response.json()
    except ValueError:
        payload = response.text
    wait = not args.no_wait or client.transport_name == "inprocess"
    if response.status_code == 202 and wait and isinstance(payload, dict) and "id" in payload:
        payload = await wait_for_job(client, payload)
    return response.status_code, payload


async def amain(argv: list[str], out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    from app.admin.manifest import manifest
    from app.api.app import app

    m = manifest(app)
    parser = build_parser(m["operations"])
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(out)
        return 2
    if args.command == "describe":
        if args.json:
            print(json.dumps(m, indent=2, ensure_ascii=False), file=out)
        else:
            for o in m["operations"]:
                print(
                    f"{o['command']:<32} {o['method']:<6} {o['path']:<62} "
                    f"{o['scope']:<8} {o['description']}",
                    file=out,
                )
            print(f"{m['count']} commands (API version {m['api_version']})", file=out)
        return 0
    op = next(o for o in m["operations"] if o["command"] == args.command)
    try:
        async with open_client(args.transport) as client:
            code, body = await execute(client, op, args)
    except UsageError as exc:
        print(f"error: {exc}", file=err)
        return 2
    except httpx.HTTPError as exc:
        print(f"error: the API could not be reached ({type(exc).__name__})", file=err)
        return 2
    # A job the command started and waited for ends the command with its outcome; a job
    # that get-job or cancel-job merely describes is data, whatever its status.
    failed = code >= 400 or (
        op["returns_job"]
        and isinstance(body, dict)
        and body.get("status") in ("failed", "cancelled")
    )
    print(_dump(body, args.json), file=err if failed else out)
    return 1 if failed else 0


def main() -> int:
    return asyncio.run(amain(sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
