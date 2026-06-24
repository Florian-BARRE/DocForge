# ====== Code Summary ======
# MCP tools for the files domain — thin wrappers over sdk.files (presigned URLs).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register file-artefact tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def get_original_url(collection_id: str, document_id: str) -> Any:
        """Get a presigned URL to download the document's original uploaded file."""
        return await sdk.files.original(collection_id, document_id)

    @mcp.tool()
    async def get_markdown_url(collection_id: str, document_id: str) -> Any:
        """Get a presigned URL for the faithful Markdown view of the document (produced by S1)."""
        return await sdk.files.markdown(collection_id, document_id)

    @mcp.tool()
    async def get_pdf_url(collection_id: str, document_id: str) -> Any:
        """Get a presigned URL for the document's canonical PDF artefact."""
        return await sdk.files.pdf(collection_id, document_id)

    @mcp.tool()
    async def get_figure_url(collection_id: str, document_id: str, block_id: str) -> Any:
        """Get a presigned URL for a figure crop PNG within the document (keyed by block_id)."""
        return await sdk.files.figure(collection_id, document_id, block_id)
