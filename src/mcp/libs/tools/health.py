# ====== Code Summary ======
# MCP tools for the health domain — thin wrapper over sdk.health.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register health tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def ping() -> Any:
        """Check DocForge connectivity — a static {"status": "ok"} when the app is serving."""
        status = await sdk.health.ping()
        return status.model_dump(mode="json")
