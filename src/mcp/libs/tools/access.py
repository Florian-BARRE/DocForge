# ====== Code Summary ======
# MCP tools for the per-collection collaborators sub-resource: list grants, set a user's
# role (upsert), and revoke a grant. All routes require collection-level ADMIN privilege
# or root. Thin wrappers over sdk.access — all path/body logic lives in libs/sdk/access.py.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """
    Register per-collection access tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def list_collection_access(collection_id: str) -> Any:
        """
        List a collection's collaborators and their per-collection roles (admin only).

        Returns each collaborator's user_id, username (if resolvable), role, who granted it,
        and when the grant was created.
        """
        return await sdk.access.list(collection_id)

    @mcp.tool()
    async def set_collection_access(
        collection_id: str,
        user_id: str,
        role: Literal["read", "write", "admin"],
    ) -> Any:
        """
        Grant or update a user's role on a collection (admin only, idempotent upsert).

        Re-setting a role updates the existing grant in-place. The grantee must be a known
        user — the backend returns 404 for phantom user ids. Roles: 'read' (search/download),
        'write' (ingest + read), 'admin' (full control including access management).
        """
        return await sdk.access.set(collection_id, user_id, role)

    @mcp.tool()
    async def revoke_collection_access(collection_id: str, user_id: str) -> Any:
        """
        Revoke a user's grant on a collection (admin only).

        Returns 404 if the user holds no grant on this collection. Root access is implicit
        and cannot be revoked via this endpoint.
        """
        return await sdk.access.revoke(collection_id, user_id)
