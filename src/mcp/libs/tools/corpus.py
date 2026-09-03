# ====== Code Summary ======
# MCP tools for the corpus document GRID + bulk operations — thin wrappers over sdk.corpus. `query`
# returns one filtered/sorted/paginated page; the three bulk ops take the shared selector (an explicit
# id list XOR a filter minus a few deselected ids), so an agent can act on "everything matching, minus
# a few" without enumerating ids. Filter/sort/selector arrive as plain dicts and are validated into the
# typed SDK models (a bad shape is a clean 422/validation error, never a silent no-op).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from docforge_sdk.models import (
    DocumentFilter,
    DocumentQueryRequest,
    DocumentSelector,
    DocumentSort,
    Pagination,
)
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register corpus grid + bulk-op tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def query_documents(
        collection_id: str,
        filter: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        """
        One filtered, sorted, paginated page of a collection's documents + the total match count.

        `filter` is the document-grid filter (e.g. {"status": ["done"], "filename": {"contains": "q3"}},
        plus a "metadata" list of {field, op, value} predicates); `sort` is {"field": ..., "direction":
        "asc"|"desc"}. Returns {total, limit, offset, rows[]} where each row is the catalogue fields +
        a {field_name: value} metadata map.
        """
        request = DocumentQueryRequest(
            filter=DocumentFilter(**filter) if filter is not None else None,
            sort=DocumentSort(**sort) if sort is not None else None,
            pagination=Pagination(limit=limit, offset=offset),
        )
        return (await sdk.corpus.query(collection_id, request)).model_dump(mode="json")

    @mcp.tool()
    async def delete_documents(collection_id: str, selector: dict[str, Any]) -> Any:
        """
        Bulk-delete documents. `selector` is {"document_ids": [...]} OR {"filter": {...}, "exclude_ids":
        [...]} (exactly one mode). Deletes everywhere (Postgres + Qdrant + S3). Returns matched vs deleted.
        """
        return (
            await sdk.corpus.bulk_delete(collection_id, DocumentSelector(**selector))
        ).model_dump(mode="json")

    @mcp.tool()
    async def set_documents_enabled(
        collection_id: str, selector: dict[str, Any], enabled: bool
    ) -> Any:
        """
        Bulk enable/disable searchability. `selector` is the shared id-XOR-filter target. A toggle is a
        Postgres flag (no re-index). Returns matched vs updated.
        """
        return (
            await sdk.corpus.bulk_set_enabled(collection_id, DocumentSelector(**selector), enabled)
        ).model_dump(mode="json")

    @mcp.tool()
    async def reingest_documents(
        collection_id: str, selector: dict[str, Any], force: bool = False
    ) -> Any:
        """
        Bulk re-run the full ingestion over the selected documents (capped fan-out). `selector` is the
        shared id-XOR-filter target. Returns matched/enqueued/capped + one job handle per enqueued run.
        """
        return (
            await sdk.corpus.bulk_reingest(collection_id, DocumentSelector(**selector), force)
        ).model_dump(mode="json")
