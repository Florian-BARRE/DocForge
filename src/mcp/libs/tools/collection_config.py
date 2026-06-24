# ====== Code Summary ======
# MCP tools for the collection-config domain — thin wrappers over sdk.config.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register collection-config tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_config_state(collection_id: str) -> Any:
        """Return a collection's full current config: contract, pipeline (redacted), and metadata schema."""
        return await sdk.config.state(collection_id)

    @mcp.tool()
    async def get_config_schema(collection_id: str) -> Any:
        """Return a collection's metadata schema (system + custom fields) — what you can filter/ingest on."""
        return await sdk.config.schema(collection_id)

    @mcp.tool()
    async def get_config_history(collection_id: str) -> Any:
        """Return a collection's config version history (newest first), for audit or rollback."""
        return await sdk.config.history(collection_id)

    @mcp.tool()
    async def update_config(collection_id: str, patch: dict[str, Any], note: str | None = None) -> Any:
        """
        Partially update a collection's config — only the keys in `patch` change. May bump the
        pipeline version and flag a reindex when the embedding model or indexing pipeline changes.
        """
        return await sdk.config.update(collection_id, patch, note)

    @mcp.tool()
    async def rollback_config(collection_id: str, version: int) -> Any:
        """Restore a collection's config to a previous history `version` (applied as a new version)."""
        return await sdk.config.rollback(collection_id, version)
