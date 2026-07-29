# ====== Code Summary ======
# MCP tools for the health domain — thin wrapper over sdk.health.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register health tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def ping() -> Any:
        """Check DocForge connectivity — a static {"status": "ok"} when the app is serving."""
        return await sdk.health.ping()
