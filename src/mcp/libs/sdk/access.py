# ====== Code Summary ======
# Per-collection access sub-API: list collaborators, set a user's role, revoke a grant.
# Mirrors the backend's access router mounted at
# /api/v1/collections/{collection_id}/access. Every call requires ADMIN role on the
# target collection (root passes implicitly).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class AccessApi(LoggerClass):
    """
    Per-collection collaborators sub-resource.

    Wraps ``/api/v1/collections/{collection_id}/access`` with three methods: list
    grants, set a user's role (upsert), and revoke a grant. All require collection-level
    ADMIN privilege (or root) on the bearer token.
    """

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(self, collection_id: str) -> Any:
        """
        List a collection's collaborators and their roles (admin only).

        Args:
            collection_id (str): UUID of the target collection.

        Returns:
            Any: AccessListResponse — collection_id, list of AccessGrantResponse, total.
        """
        # 1. GET the collaborators for this collection
        return await self._t.get(f"/collections/{collection_id}/access")

    async def set(
        self,
        collection_id: str,
        user_id: str,
        role: Literal["read", "write", "admin"],
    ) -> Any:
        """
        Grant or update a user's role on the collection (admin only, idempotent upsert).

        Re-setting a role updates the existing grant. The grantee must be a known user —
        the backend returns 404 for phantom user ids.

        Args:
            collection_id (str): UUID of the target collection.
            user_id (str): UUID of the user to grant access to.
            role (str): Per-collection role — ``"read"``, ``"write"``, or ``"admin"``.

        Returns:
            Any: AccessGrantResponse — user_id, username, role, granted_by, created_at.
        """
        # 1. PUT the role to the user's access sub-resource on this collection
        return await self._t.put(
            f"/collections/{collection_id}/access/{user_id}",
            {"role": role},
        )

    async def revoke(self, collection_id: str, user_id: str) -> Any:
        """
        Revoke a user's grant on the collection (admin only).

        Returns 404 from the backend if the user holds no grant on this collection.

        Args:
            collection_id (str): UUID of the target collection.
            user_id (str): UUID of the user whose grant to revoke.

        Returns:
            Any: RevokeAccessResponse — revoked (bool), collection_id, user_id.
        """
        # 1. DELETE the user's grant from this collection
        return await self._t.delete(f"/collections/{collection_id}/access/{user_id}")
