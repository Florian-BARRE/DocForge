# ====== Code Summary ======
# MCP tools for the collections domain — thin wrappers over sdk.collections.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register collection tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_collections() -> Any:
        """List all document collections (id, name, formats, embedding model, created_at)."""
        return await sdk.collections.list()

    @mcp.tool()
    async def create_collection(
        name: str,
        supported_formats: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        locality_policy: str | None = None,
        embedding_model: str | None = None,
        unknown_field_policy: str | None = None,
        pipeline: dict[str, Any] | None = None,
        metadata_schema: list[dict[str, Any]] | None = None,
    ) -> Any:
        """
        Create a collection. Only `name` is required — every other knob falls back to a sensible
        server default (formats, 100 MB cap, BAAI/bge-m3, external_allowed). Supply `pipeline` or
        `metadata_schema` only for advanced setups; the resolved config is echoed back.
        """
        return await sdk.collections.create(
            name=name,
            supported_formats=supported_formats,
            max_file_size_bytes=max_file_size_bytes,
            locality_policy=locality_policy,
            embedding_model=embedding_model,
            unknown_field_policy=unknown_field_policy,
            pipeline=pipeline,
            metadata_schema=metadata_schema,
        )

    @mcp.tool()
    async def delete_collection(collection_id: str) -> Any:
        """Delete a collection and all its data (Postgres + Qdrant + non-shared S3 blobs). Irreversible."""
        return await sdk.collections.delete(collection_id)
