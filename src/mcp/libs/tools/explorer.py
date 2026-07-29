# ====== Code Summary ======
# MCP tools for the document explorer domain — thin wrappers over sdk.explorer (the read-only
# browse surface: catalogue, facts, pages, IR, chunks, toggles, and the coherent delete).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register document explorer tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_documents(collection_id: str) -> Any:
        """Return a collection's documents, newest first — the browse catalogue."""
        return await sdk.explorer.list_documents(collection_id)

    @mcp.tool()
    async def get_document(document_id: str) -> Any:
        """Return one document's full facts and resolved document-level metadata."""
        return await sdk.explorer.get_document(document_id)

    @mcp.tool()
    async def get_document_pages(document_id: str) -> Any:
        """Return a document's pages, in order — geometry, routing and the render blob reference."""
        return await sdk.explorer.get_pages(document_id)

    @mcp.tool()
    async def get_document_ir(document_id: str) -> Any:
        """Return the document's full canonical IR — blocks, tables, figures, enrichments (can be large)."""
        return await sdk.explorer.get_ir(document_id)

    @mcp.tool()
    async def get_document_chunks(document_id: str) -> Any:
        """Return a document's retrieval chunks — enriched text, composition and generated metadata."""
        return await sdk.explorer.get_chunks(document_id)

    @mcp.tool()
    async def delete_document(document_id: str) -> Any:
        """Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge). Irreversible."""
        return await sdk.explorer.delete_document(document_id)

    @mcp.tool()
    async def set_chunk_enabled(chunk_id: str, enabled: bool) -> Any:
        """Toggle one chunk's searchability (reversible, no re-embed)."""
        return await sdk.explorer.set_chunk_enabled(chunk_id, enabled)

    @mcp.tool()
    async def set_chunks_enabled(chunk_ids: list[str], enabled: bool) -> Any:
        """Toggle several chunks' searchability to the same state in one call (multi-select)."""
        return await sdk.explorer.set_chunks_enabled(chunk_ids, enabled)
