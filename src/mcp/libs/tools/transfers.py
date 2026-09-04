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

# ====== Local Project Imports ======
from ..path_guard import PathGuard


def register(mcp: FastMCP, sdk: AsyncClient, path_guard: PathGuard) -> None:
    """Register transfer (export/import) tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
        path_guard (PathGuard): Resolves/confines `file_path` before it reaches the SDK — a no-op
            on stdio, but on streamable-HTTP it refuses any path outside the configured inbox (or
            everything, if no inbox is configured) so a remote caller can never read an arbitrary
            file off the MCP container's filesystem.
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
        `file_path` is read from the MCP SERVER's own filesystem, NOT the caller's local disk. On
        stdio that is any local path; on streamable-HTTP the operator must stage the bundle inside
        the configured upload inbox (MCP_UPLOAD_DIR) first (e.g. a shared volume) — a path outside
        it, or no inbox configured at all, is refused. Returns the transfer handle immediately
        (202) — poll get_transfer for progress.
        """
        resolved = path_guard.resolve(file_path)
        accepted = await sdk.transfers.import_collection(resolved, target_name=target_name)
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
