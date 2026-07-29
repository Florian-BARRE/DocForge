# ====== Code Summary ======
# MCP tools for the auth domain — root-owned API-key management (create / list / revoke).
# Thin wrappers over sdk.auth — all path/body logic lives in libs/sdk/auth.py. DocForge's
# auth model is keys-only: there is no login/me/users surface to wrap.
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
    async def create_api_key(name: str, permissions: dict[str, Any] | None = None) -> Any:
        """
        Create a new root-owned API key.

        IMPORTANT: the plaintext key is returned EXACTLY ONCE in the response (the `key`
        field) and is never retrievable again — only its hash is stored server-side. Capture
        the `key` value from the response immediately before discarding it.

        `permissions` scopes the key's capabilities and collections (null/omitted = full
        access, the root shape).
        """
        return await sdk.auth.create_key(name, permissions)

    @mcp.tool()
    async def list_api_keys() -> Any:
        """
        List every API key — shows prefixes and metadata, never the plaintext key or hash.

        Includes both active and revoked keys so the full audit trail is visible.
        """
        return await sdk.auth.list_keys()

    @mcp.tool()
    async def revoke_api_key(key_id: str) -> Any:
        """Soft-revoke an API key (idempotent — the record remains for audit)."""
        return await sdk.auth.revoke_key(key_id)
