# ====== Code Summary ======
# MCP tools for the discovery domain — thin wrappers over sdk.discovery.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register discovery tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_discovery(collection_id: str | None = None) -> Any:
        """
        Describe every DocForge endpoint and its dynamic choices — the self-documenting catalogue.

        Call this first to learn what operations exist and which metadata fields a collection
        supports for search filters and ingest. Pass a collection_id to resolve collection-scoped
        choices (filterable fields, weights, ingest metadata).
        """
        return await sdk.discovery.get(collection_id)
