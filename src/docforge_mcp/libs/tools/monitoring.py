# ====== Code Summary ======
# MCP tools for the monitoring domain — thin wrappers over sdk.monitoring.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register monitoring tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_queue_status() -> Any:
        """Return queue depth, per-status job counts, and recent throughput."""
        return await sdk.monitoring.queue()

    @mcp.tool()
    async def get_workers() -> Any:
        """Return the live worker fleet with per-worker load/resource gauges."""
        return await sdk.monitoring.workers()

    @mcp.tool()
    async def get_monitoring_overview() -> Any:
        """Return an aggregate operational snapshot (queue + workers) with a timestamp."""
        return await sdk.monitoring.overview()

    @mcp.tool()
    async def get_monitoring_discovery() -> Any:
        """Return the descriptor that drives the monitoring dashboard."""
        return await sdk.monitoring.discovery()
