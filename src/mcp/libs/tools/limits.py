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
        Return a collection's configured resource limits and current live usage.

        Reports the per-collection in-flight job cap and budget cap in USD, alongside the
        current in-flight count and cumulative spend. A null cap means unlimited.
        """
        return await sdk.limits.get(collection_id)

    @mcp.tool()
    async def update_collection_limits(
        collection_id: str,
        max_in_flight: int | None = None,
        budget_cap_usd: float | None = None,
    ) -> Any:
        """
        Replace a collection's resource limits (PUT — both caps are set in one call).

        Pass null for a cap to clear it (unlimited). The server rejects a value of 0
        for either cap (use null to express 'no limit'). Responds with the refreshed
        caps and live usage. Changing limits never triggers reindex.
        """
        return await sdk.limits.update(
            collection_id,
            max_in_flight=max_in_flight,
            budget_cap_usd=budget_cap_usd,
        )
