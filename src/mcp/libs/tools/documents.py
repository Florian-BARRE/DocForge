# ====== Code Summary ======
# MCP tools for the documents domain — thin wrappers over sdk.documents.

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
    async def ingest_document(
        collection_id: str, file_path: str, metadata: dict[str, Any] | None = None
    ) -> Any:
        """
        Upload a local file into a collection and start indexing (async). Returns a doc_id and
        job_id — poll get_job(job_id) or get_document() until status is 'done'. `file_path` must be
        an absolute path readable by the MCP server. Optional `metadata` is validated against the
        collection schema.
        """
        return await sdk.documents.ingest(collection_id, file_path, metadata)

    @mcp.tool()
    async def list_documents(
        collection_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Any:
        """
        List documents in a collection. Filter by `status` (pending/running/done/error), paginate
        with limit/offset, sort by created_at|filename|status|file_size (asc|desc).
        """
        return await sdk.documents.list(
            collection_id, status=status, limit=limit, offset=offset,
            sort_by=sort_by, sort_order=sort_order,
        )

    @mcp.tool()
    async def get_document(collection_id: str, document_id: str) -> Any:
        """
        Full document record: status, page/chunk/block counts, file availability (original/pdf/
        markdown), indexing state, staleness, and any pipeline errors.
        """
        return await sdk.documents.get(collection_id, document_id)

    @mcp.tool()
    async def update_document(
        collection_id: str, document_id: str, metadata: dict[str, Any], reindex: bool = False
    ) -> Any:
        """
        Merge a metadata patch into a document's user metadata (a null value removes a key).
        Set reindex=true to sync the changed fields into the live search index.
        """
        return await sdk.documents.update(collection_id, document_id, metadata, reindex)

    @mcp.tool()
    async def reingest_document(collection_id: str, document_id: str, force: bool = False) -> Any:
        """
        Re-run the full pipeline for a document. The Merkle cache keeps unchanged stages cheap
        unless force=true, which rebuilds every stage from scratch.
        """
        return await sdk.documents.reingest(collection_id, document_id, force)

    @mcp.tool()
    async def delete_document(collection_id: str, document_id: str) -> Any:
        """Delete a document and all its data (cascade across Postgres / Qdrant / S3). Irreversible."""
        return await sdk.documents.delete(collection_id, document_id)
