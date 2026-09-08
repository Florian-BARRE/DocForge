# ====== Code Summary ======
# MCP tools for the capabilities domain — thin wrapper over sdk.capabilities.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register capabilities tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_capabilities() -> Any:
        """Report what THIS DocForge deployment can do right now: version, GPU presence, reachable
        sidecars and available pipeline capabilities."""
        capabilities = await sdk.capabilities.capabilities()
        return capabilities.model_dump(mode="json")
