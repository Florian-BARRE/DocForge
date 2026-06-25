# ====== Code Summary ======
# MCP tools for the per-collection resource-limits domain — thin wrappers over sdk.limits.
#
# NOTE: The two SSE endpoints (GET /collections/{id}/documents/stream and
# GET /monitoring/stream) are intentionally NOT exposed as tools here. MCP has no streaming
# primitive — tools must return a single result synchronously. Callers should use the snapshot
# REST equivalents instead: sdk.documents.list() for document state and sdk.monitoring.overview()
# / sdk.monitoring.queue() for operational state.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """
    Register per-collection resource-limits tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_collection_limits(collection_id: str) -> Any:
        """
        Return a collection's configured in-flight cap and current live usage.

        Reports the per-collection max_in_flight cap alongside the current in_flight
        count. A null cap means unlimited.
        """
        return await sdk.limits.get(collection_id)

    @mcp.tool()
    async def update_collection_limits(
        collection_id: str,
        max_in_flight: int | None = None,
    ) -> Any:
        """
        Replace a collection's in-flight cap (PUT — the cap is set explicitly).

        Pass null to clear the cap (unlimited). The server rejects a value of 0
        (use null to express 'no limit'). Responds with the refreshed cap and live
        in-flight count. Changing limits never triggers reindex.
        """
        return await sdk.limits.update(
            collection_id,
            max_in_flight=max_in_flight,
        )
