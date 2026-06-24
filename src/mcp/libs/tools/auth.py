# ====== Code Summary ======
# MCP tools for the auth domain: login, me, and API-key management (create / list / revoke).
# Thin wrappers over sdk.auth — all path/body logic lives in libs/sdk/auth.py.
#
# IMPORTANT — login semantics in MCP context:
# The MCP server itself authenticates to DocForge using the static DOCFORGE_API_TOKEN
# configured at startup (set on the shared transport as a default Authorization header).
# The `login` tool returns a JWT for informational or admin use only — it does NOT
# reconfigure the transport. Use it to obtain a token for a user, not to control MCP auth.
#
# IMPORTANT — create_api_key plaintext disclosure:
# The plaintext key is returned EXACTLY ONCE in the `create_api_key` response (the `key`
# field). The backend never stores it in plaintext — only the hash is persisted. Callers
# must capture the key immediately; it cannot be retrieved again.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """
    Register auth tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def login(username: str, password: str) -> Any:
        """
        Authenticate a username/password pair against DocForge and return a JWT token.

        This is the only public auth endpoint — no bearer token is required to call it.
        The returned JWT can be used as a DocForge API token by other tools (e.g. set as
        DOCFORGE_API_TOKEN). The MCP server's own outbound auth uses the static token
        configured at startup — calling this tool does NOT reconfigure MCP transport auth.
        """
        return await sdk.auth.login(username, password)

    @mcp.tool()
    async def get_me() -> Any:
        """
        Return the authenticated principal's identity and per-collection grants.

        Uses the bearer token already configured on the MCP server (DOCFORGE_API_TOKEN).
        Root users receive an empty grants list — root has implicit admin on every collection.
        """
        return await sdk.auth.me()

    @mcp.tool()
    async def create_api_key(name: str) -> Any:
        """
        Create a new API key for the current user.

        IMPORTANT: the plaintext key is returned EXACTLY ONCE in the response (the `key`
        field) and is never retrievable again — only its hash is stored server-side. Capture
        the `key` value from the response immediately before discarding it.

        The `prefix` field (first few characters) is always safe to display for identification.
        """
        return await sdk.auth.create_api_key(name)

    @mcp.tool()
    async def list_api_keys() -> Any:
        """
        List the current user's API keys — shows prefixes and metadata, never the plaintext key or hash.

        Includes both active and revoked keys so the full audit trail is visible.
        """
        return await sdk.auth.list_api_keys()

    @mcp.tool()
    async def revoke_api_key(key_id: str) -> Any:
        """
        Revoke one of the current user's own API keys (soft revoke).

        A user can only revoke their own keys — attempting to revoke another user's key or
        an already-revoked key returns 404 from the backend (no information about other users
        is leaked). Revocation is soft: the key record remains for audit.
        """
        return await sdk.auth.revoke_api_key(key_id)
