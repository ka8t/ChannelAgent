"""The one vetted built-in MCP server shipped for #116: the current time in an IANA
timezone. Launched over stdio by app.mcp.manager with a cleared environment (the
SDK's own default: only HOME/LOGNAME/PATH/SHELL/TERM/USER, none of this
application's secrets, app.mcp.manager module docstring). `MCP_HTTP_PORT` set in the
environment instead runs it over streamable HTTP on localhost — used only to
validate that transport (#116's own "one HTTP server answers a call"), never how a
real turn reaches it (no HTTP built-in is registered by default).
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

from mcp.server.fastmcp import FastMCP

_http_port = os.environ.get("MCP_HTTP_PORT")
mcp = FastMCP("time", host="127.0.0.1", port=int(_http_port) if _http_port else 8000)


@mcp.tool()
def get_time(timezone: str) -> str:
    """Get the current date and time in an IANA timezone, e.g. "Europe/Paris"."""
    if timezone not in available_timezones():
        return f"error: unknown timezone {timezone!r}"
    return datetime.now(ZoneInfo(timezone)).isoformat()


if __name__ == "__main__":
    mcp.run(transport="streamable-http" if _http_port else "stdio")
