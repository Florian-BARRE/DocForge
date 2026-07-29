# ====== Code Summary ======
# MCP tools for the documents domain — thin wrappers over sdk.documents (the admission path).
# Browsing an admitted document (list/get/pages/ir/chunks/delete) lives in the explorer tools.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """Register document tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def upload_document(
        file_path: str, collection_id: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file into a collection and enqueue its ingestion (async — poll
        get_job(job_id) or get_document(document_id) for status). `file_path` must be an
        absolute path readable by the MCP server. `metadata` is validated against the
        collection's declared schema (unknown field names are rejected).
        """
        return await sdk.documents.upload(file_path, collection_id, metadata)

    @mcp.tool()
    async def set_document_enabled(document_id: str, enabled: bool) -> Any:
        """Toggle a document's searchability (reversible, no re-ingest)."""
        return await sdk.documents.set_enabled(document_id, enabled)
