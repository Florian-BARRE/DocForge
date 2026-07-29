# ====== Code Summary ======
# Auth sub-API: API-key management under /api/v1/auth/keys (create / list / revoke). The
# DocForge auth model is keys-only (no login/me/users surface) — keys are root-owned and
# creation returns the plaintext exactly once.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class AuthApi(LoggerClass):
    """Root-owned API-key management endpoints."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def create_key(self, name: str, permissions: dict[str, Any] | None = None) -> Any:
        """
        Create an API key and return its plaintext exactly once.

        Args:
            name (str): Human-readable label for the key.
            permissions (dict | None): Per-key capability + collection scope; None = full access.

        Returns:
            Any: CreatedKey — id, name, prefix, permissions, created_at, key (plaintext, once).
        """
        # 1. Only send permissions when the caller actually scoped the key
        body: dict[str, Any] = {"name": name}
        if permissions is not None:
            body["permissions"] = permissions
        return await self._t.post("/auth/keys", body)

    async def list_keys(self) -> Any:
        """List every API key — metadata only, never the hash or plaintext (includes revoked)."""
        return await self._t.get("/auth/keys")

    async def revoke_key(self, key_id: str) -> Any:
        """
        Soft-revoke an API key (idempotent — stamps revoked_at).

        Args:
            key_id (str): UUID of the key to revoke.
        """
        return await self._t.delete(f"/auth/keys/{key_id}")
