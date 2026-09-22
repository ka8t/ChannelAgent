"""End-to-end test for #116's own Done-when: a turn whose agent is allowed one MCP
tool calls the real built-in "time" server and answers from the result, with
exactly one McpCall row recorded. The chat model is mocked (a real HTTPServer, per
this repo's test conventions); the MCP server is the real stdio subprocess.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import tools as tools_module
from app.db.models import Channel, McpCall


class _Scripted(BaseHTTPRequestHandler):
    """Replies to /v1/chat/completions from a queue; the probe request (#115,
    tool_choice=required) is answered separately, matched by that field, so the
    queue only needs the turn's own rounds in order.
    """

    responses: list = []
    requests: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/v1/chat/completions":  # no tokenizer on this mock (#87 falls back)
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.loads(raw)
        type(self).requests.append(body)
        if body.get("tool_choice") == "required":
            # The #115 capability probe: always answer with a tool call.
            payload = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "probe",
                                    "type": "function",
                                    "function": {"name": "_capability_probe", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            }
        else:
            payload = type(self).responses.pop(0)
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _message(content="", tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


@pytest.fixture
async def env(fresh_db, monkeypatch):
    import httpx

    from app.api import deps
    from app.api.app import app
    from app.config import get_settings
    from app.db.session import init_db

    _Scripted.requests = []
    _Scripted.responses = []
    server = HTTPServer(("127.0.0.1", 0), _Scripted)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("LLAMA_SERVER_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("API_SERVER_KEY", "Zq8vT3mK9xW2pL7nR4bY6cH1dF5gJ0sA")
    get_settings.cache_clear()
    deps.reset_failure_state()
    tools_module.reset_capability_check()
    await init_db()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    headers = {"Authorization": "Bearer Zq8vT3mK9xW2pL7nR4bY6cH1dF5gJ0sA"}
    async with httpx.AsyncClient(transport=transport, base_url="http://t", headers=headers) as api:
        user = (await api.post("/users", json={"display_name": "Sam"})).json()["id"]
        api.user = user
        yield api
    from app.mcp.manager import manager as shared_manager

    await shared_manager.reset()
    app.dependency_overrides.clear()
    server.shutdown()
    get_settings.cache_clear()
    deps.reset_failure_state()
    tools_module.reset_capability_check()


async def test_a_turn_calls_the_built_in_server_and_answers_from_the_result(env):
    mcp_server = await env.post(
        "/mcp/servers", json={"name": "time", "protocol": "stdio", "builtin_id": "time"}
    )
    assert mcp_server.status_code == 201, mcp_server.text

    agent = await env.post(
        f"/users/{env.user}/agents",
        json={"name": "helper", "tools": ["mcp__time__get_time"]},
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    _Scripted.responses = [
        _message(
            tool_calls=[
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "mcp__time__get_time",
                        "arguments": '{"timezone": "UTC"}',
                    },
                }
            ]
        ),
        _message(content="It's a good time to check the clock."),
    ]

    from app.graph import run_turn

    reply = await run_turn(Channel.TELEGRAM, "555", agent_id, "what time is it?")

    assert reply == "It's a good time to check the clock."

    # The tool call really reached the built-in server: the message sent back for
    # the final round carries its real (non-mocked) answer, framed as data.
    final_request = _Scripted.requests[-1]
    tool_message = next(m for m in final_request["messages"] if m.get("role") == "tool")
    assert "untrusted data" in tool_message["content"]
    assert "T" in tool_message["content"]  # the real ISO 8601 datetime from the built-in

    # Exactly one McpCall row for the one call the turn made.
    from sqlalchemy import select

    from app.db.session import session_scope

    async with session_scope() as session:
        rows = list((await session.execute(select(McpCall))).scalars())
    assert len(rows) == 1
    row = rows[0]
    assert (row.agent_id, row.server_name, row.tool_name, row.status) == (
        agent_id,
        "time",
        "get_time",
        "ok",
    )


async def test_an_agent_with_no_tools_never_probes_or_uses_the_loop(env):
    agent = await env.post(f"/users/{env.user}/agents", json={"name": "plain"})
    agent_id = agent.json()["id"]
    _Scripted.responses = [_message(content="plain reply")]

    from app.graph import run_turn

    reply = await run_turn(Channel.TELEGRAM, "555", agent_id, "hello")

    assert reply == "plain reply"
    # No probe request: the tool_choice=required branch in _Scripted was never hit.
    assert all(r.get("tool_choice") is None for r in _Scripted.requests)
