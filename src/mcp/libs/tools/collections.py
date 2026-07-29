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
        """List every collection with its full contract (schema, pipeline, search blobs)."""
        return await sdk.collections.list()

    @mcp.tool()
    async def get_collection(collection_id: str) -> Any:
        """Return one collection's full contract."""
        return await sdk.collections.get(collection_id)

    @mcp.tool()
    async def create_collection(
        name: str,
        supported_formats: list[str],
        max_file_size_bytes: int,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
    ) -> Any:
        """
        Create a collection from A to Z. `fields` is the FULL metadata schema declared up
        front (each item: field_name, field_type, required, filterable, lexical, semantic,
        enum_values, origin, scope) — the vector space is fixed at creation and cannot grow
        later. `pipeline` is the ingestion graph blob; omit it to use the product default
        (all stages wired).
        """
        return await sdk.collections.create(
            name, supported_formats, max_file_size_bytes, fields=fields, pipeline=pipeline
        )

    @mcp.tool()
    async def update_collection(
        collection_id: str,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
        search: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> Any:
        """
        Patch identity/limits, the metadata schema (applied by diff against field_name — an
        omitted field is removed), and/or the config blobs (pipeline / search graphs, each
        validated before storage). A change to the searchable schema flips needs_reindex.
        """
        return await sdk.collections.update(
            collection_id,
            name=name,
            supported_formats=supported_formats,
            max_file_size_bytes=max_file_size_bytes,
            fields=fields,
            pipeline=pipeline,
            search=search,
            note=note,
        )

    @mcp.tool()
    async def delete_collection(collection_id: str) -> Any:
        """Delete a collection (404 when unknown). Irreversible."""
        return await sdk.collections.delete(collection_id)
