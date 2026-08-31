# ====== Code Summary ======
# MCP tools for the transfers domain (collection export/import) — thin wrappers over sdk.transfers.
# A completed export's bundle bytes are NEVER streamed back through an MCP tool result (a bundle can
# be multi-GB); get_export_download_ref instead points the caller at the REST download endpoint,
# which they hit directly (or via docforge_sdk's own streaming transfers.download_export).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """Register transfer (export/import) tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def export_collection(collection_id: str) -> Any:
        """
        Open an asynchronous export of a whole collection into a portable `.dcexport` bundle
        (404 when the collection is unknown). Returns the transfer handle immediately (202) —
        poll get_transfer with its transfer_id for progress.
        """
        accepted = await sdk.transfers.export_collection(collection_id)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def import_collection(file_path: str, target_name: str | None = None) -> Any:
        """
        Import a `.dcexport` bundle as a brand-new collection (asynchronous, no recompute).
        `file_path` is read from the MCP SERVER's own filesystem, NOT the caller's local disk —
        for a remote MCP deployment the operator must stage the bundle there first (e.g. a shared
        volume). Returns the transfer handle immediately (202) — poll get_transfer for progress.
        """
        accepted = await sdk.transfers.import_collection(file_path, target_name=target_name)
        return accepted.model_dump(mode="json")

    @mcp.tool()
    async def get_transfer(transfer_id: str) -> Any:
        """
        Poll one transfer's live status — progress, stage, counts, error, and (once a done
        export) its bundle's size_bytes/expires_at, or (once a done import) the new
        collection_id/collection_name.
        """
        status = await sdk.transfers.get_transfer(transfer_id)
        return status.model_dump(mode="json")

    @mcp.tool()
    async def get_export_download_ref(transfer_id: str) -> Any:
        """
        Return how to fetch a completed export's bundle WITHOUT streaming its bytes through this
        tool (a bundle can be multi-GB). Poll get_transfer first; once status is "done" for an
        export, GET download_path against the DocForge REST API (bearer-authed) — or, from a
        Python caller, use docforge_sdk's transfers.download_export(transfer_id), which streams
        the bytes in bounded chunks.
        """
        status = await sdk.transfers.get_transfer(transfer_id)
        return {
            "transfer_id": status.transfer_id,
            "kind": status.kind,
            "status": status.status,
            "size_bytes": status.size_bytes,
            "expires_at": status.expires_at.isoformat() if status.expires_at else None,
            "download_path": f"/api/v1/transfers/{status.transfer_id}/download",
        }
