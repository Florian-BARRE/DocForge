# ====== Code Summary ======
# MCP tools for the pipelines domain — thin wrappers over sdk.pipelines (the read-only slice
# of the design surface: discovery + the lean palette/blob payload).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register pipeline design tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_pipeline_surfaces() -> Any:
        """Discover the available pipeline design surfaces (ingest / search) and their URLs."""
        return await sdk.pipelines.list_surfaces()

    @mcp.tool()
    async def get_pipeline_design(key: str, full: bool = False) -> Any:
        """
        Open a pipeline design surface: the block palette, the default blob, and any
        validation issues. `key` is "ingest" or "search"; `full=true` adds the advanced
        palette blocks (run_inputs, mechanics, artefacts).
        """
        return await sdk.pipelines.get_design(key, full=full)
