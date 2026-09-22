"""Mutation check for #116 (MCP client and server registry): one deliberate defect
per new control, the MCP test files judged on whether they notice. Restores every
file in a finally. Run:
    .venv/bin/python scripts/dev/mutations/issue_116_mutations.py
"""

import subprocess

MANAGER = "app/mcp/manager.py"
ADMIN = "app/admin/mcp.py"
CATALOGUE = "app/mcp/catalogue.py"
GRAPH = "app/graph.py"

TESTS = [
    "tests/test_mcp_manager.py",
    "tests/test_mcp_admin.py",
    "tests/test_mcp_catalogue.py",
    "tests/test_mcp_graph_wiring.py",
]

muts = [
    (
        "A a disabled tool can still be called",
        MANAGER,
        'if tool_name in self.config.disabled_tools:\n            raise McpServerError(f"{tool_name!r} is disabled on {self.config.name!r}")',
        "if False:\n            raise McpServerError('unreachable')",
    ),
    (
        "B the per-call timeout removed",
        MANAGER,
        "with anyio.fail_after(self.config.timeout_seconds):\n                    result = await session.call_tool(tool_name, arguments)",
        "result = await session.call_tool(tool_name, arguments)",
    ),
    (
        "C the concurrency limit removed",
        MANAGER,
        "async with self._semaphore:",
        "if True:",
    ),
    (
        "D the backoff after a failed connection is skipped",
        MANAGER,
        "if now < self._next_retry_at:",
        "if False:",
    ),
    (
        "E the result-size cap removed",
        MANAGER,
        "return text[: self.config.result_max_bytes], bool(result.isError)",
        "return text, bool(result.isError)",
    ),
    (
        "F any builtin_id is accepted, not just a vetted one",
        ADMIN,
        "if builtin_id not in BUILTIN_REGISTRY:",
        "if False:",
    ),
    (
        "G a duplicate server name is accepted",
        ADMIN,
        "if await _named(session, name) is not None:\n        raise McpServerNameTakenError(f\"A server named {name!r} already exists\")",
        "if False:\n        raise McpServerNameTakenError('unreachable')",
    ),
    (
        "H the concurrency_limit bound removed",
        ADMIN,
        "if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:",
        "if isinstance(value, bool) or not isinstance(value, int):",
    ),
    (
        "I the timeout_seconds bound removed",
        ADMIN,
        "if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 600:",
        "if isinstance(value, bool) or not isinstance(value, int):",
    ),
    (
        "J the catalogue offers a tool the agent was never granted",
        CATALOGUE,
        "if name in allowed:",
        "if True:",
    ),
    (
        "K the catalogue still offers a disabled tool",
        CATALOGUE,
        'if tool.name in server.config.disabled_tools:\n                continue',
        "if False:\n                continue",
    ),
    (
        "L a turn tries tools even when the agent was granted none",
        GRAPH,
        "if tools_allowed and await tools_are_supported(client)",
        "if True",
    ),
]

for name, f, a, b in muts:
    orig = open(f).read()
    assert a in orig, f"{name}: pattern not found in {f}"
    new = orig.replace(a, b, 1)
    assert new != orig, name
    open(f, "w").write(new)
    try:
        r = subprocess.run(
            [".venv/bin/python", "-m", "pytest", *TESTS, "-q", "--no-header", "-p", "no:cacheprovider"],
            capture_output=True, text=True,
        )
        print(name, "->", r.stdout.strip().splitlines()[-1])
    finally:
        open(f, "w").write(orig)
