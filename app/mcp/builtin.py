"""Registry of vetted built-in MCP servers (#116): `stdio` transport never runs an
admin-supplied command — that would be arbitrary code execution as a feature
(docs/MCP_EXTENSION.md threat table). It only ever launches one of these, by id,
as `sys.executable -m <module>` inside this same virtualenv.
"""

REGISTRY: dict[str, str] = {
    "time": "app.mcp.builtin_servers.time_server",
}
