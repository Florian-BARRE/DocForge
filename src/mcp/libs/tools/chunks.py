# ====== Code Summary ======
# MCP tools for the chunks domain — thin wrappers over sdk.chunks.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register chunk tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_chunks(
        collection_id: str, document_id: str, limit: int = 50, offset: int = 0
    ) -> Any:
        """List a document's chunks in reading order (paginated). Chunks are the atomic retrieval unit."""
        return await sdk.chunks.list(collection_id, document_id, limit=limit, offset=offset)

    @mcp.tool()
    async def get_chunk(collection_id: str, document_id: str, chunk_id: str) -> Any:
        """Fully materialise one chunk: raw_text, embed_text, token_count, and provenance."""
        return await sdk.chunks.get(collection_id, document_id, chunk_id)

    @mcp.tool()
    async def update_chunk(
        collection_id: str,
        document_id: str,
        chunk_id: str,
        raw_text: str | None = None,
        embed_text: str | None = None,
        reindex: bool = False,
    ) -> Any:
        """
        Manually correct a chunk's text. Provide raw_text and/or embed_text (at least one).
        Set reindex=true to re-embed the chunk's content vectors from the new embed_text.
        """
        return await sdk.chunks.update(
            collection_id, document_id, chunk_id,
            raw_text=raw_text, embed_text=embed_text, reindex=reindex,
        )
