# ====== Code Summary ======
# Auth sub-API: login (public), me (identity + grants), and API-key management (create / list /
# revoke). Mirrors the backend's auth router mounted at /api/v1/auth.
# NOTE: login returns a JWT for informational/admin use. The MCP server itself authenticates to
# DocForge using a static bearer token configured via DOCFORGE_API_TOKEN — it does NOT use the
# returned JWT to reconfigure the shared transport.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class AuthApi(LoggerClass):
    """
    Auth endpoints: login, identity, and per-user API-key management.

    Wraps ``/api/v1/auth`` and exposes the five leaf routes as typed async methods.
    """

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def login(self, username: str, password: str) -> Any:
        """
        Authenticate a username/password pair and return a signed JWT access token.

        This is the only public endpoint — no bearer token required to call it. The
        MCP server's own outbound auth uses a static DOCFORGE_API_TOKEN, not this JWT.

        Args:
            username (str): Login handle.
            password (str): Plaintext password (transmitted over TLS, never stored).

        Returns:
            Any: LoginResponse — access_token (JWT), token_type, user summary.
        """
        # 1. POST credentials to the public login endpoint
        return await self._t.post("/auth/login", {"username": username, "password": password})

    async def me(self) -> Any:
        """
        Return the calling principal's identity and per-collection grants.

        Uses the bearer token already configured on the transport (DOCFORGE_API_TOKEN).
        Root users receive an empty grants list — root has implicit admin everywhere.

        Returns:
            Any: MeResponse — user summary + list of CollectionGrantSummary.
        """
        # 1. GET the caller's identity from the authenticated endpoint
        return await self._t.get("/auth/me")

    async def create_api_key(self, name: str) -> Any:
        """
        Create a new API key for the current user and return the plaintext key.

        The plaintext key is returned EXACTLY ONCE and never retrievable again — only its
        hash is stored server-side. Clients must capture the ``key`` field immediately.

        Args:
            name (str): Human-readable label for the key (1-255 chars).

        Returns:
            Any: ApiKeyCreatedResponse — id, name, prefix, key (plaintext, shown once),
                 created_at.
        """
        # 1. POST the create request; the plaintext key surfaces in the response body only
        return await self._t.post("/auth/keys", {"name": name})

    async def list_api_keys(self) -> Any:
        """
        List the current user's API keys — prefixes only, never plaintext or hash.

        Returns:
            Any: ApiKeyListResponse — list of ApiKeySummary + total count.
        """
        # 1. GET the current user's key list (prefixes safe to display)
        return await self._t.get("/auth/keys")

    async def revoke_api_key(self, key_id: str) -> Any:
        """
        Revoke one of the current user's own API keys (soft revoke).

        A user can only revoke their own keys. Attempting to revoke an unknown, foreign,
        or already-revoked key yields a 404 from the backend.

        Args:
            key_id (str): UUID of the API key to revoke.

        Returns:
            Any: ApiKeyRevokeResponse — revoked (bool) + id.
        """
        # 1. DELETE the key scoped to the current user
        return await self._t.delete(f"/auth/keys/{key_id}")
