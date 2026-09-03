# ====== Code Summary ======
# MCP tools for the auth domain — root-owned API-key management (create / list / revoke / rotate).
# Thin wrappers over sdk.auth — all path/body logic lives in docforge_sdk. DocForge's auth model is
# keys-only: there is no login/me/users surface to wrap.
#
# IMPORTANT — create_api_key / rotate_api_key plaintext disclosure:
# The plaintext key is returned EXACTLY ONCE in the response (the `key` field). The backend never
# stores it in plaintext — only the hash is persisted. Callers must capture the key immediately; it
# cannot be retrieved again.
#
# IMPORTANT — rotate_api_key "keep unchanged" semantics:
# The MCP tool boundary cannot distinguish "argument omitted" from "argument explicitly null" (every
# FastMCP tool call passes every parameter, using its Python default when the caller didn't set it).
# So `name` / `permissions` / `expires_at` left at their default `None` are treated as "keep the
# source key's current value" (mapped to the SDK's Ellipsis sentinel) — there is no way to explicitly
# clear permissions back to full access or expiry back to never via this tool; issue a new key instead.

from __future__ import annotations

# ====== Standard Library Imports ======
from datetime import datetime
from types import EllipsisType
from typing import Any

# ====== Third-Party Library Imports ======
from docforge_sdk import AsyncClient, KeyPermissions
from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, sdk: AsyncClient) -> None:
    """
    Register auth tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (AsyncClient): The DocForge API client.
    """

    @mcp.tool()
    async def create_api_key(
        name: str,
        permissions: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> Any:
        """
        Create a new root-owned API key.

        IMPORTANT: the plaintext key is returned EXACTLY ONCE in the response (the `key`
        field) and is never retrievable again — only its hash is stored server-side. Capture
        the `key` value from the response immediately before discarding it.

        `permissions` scopes the key's capabilities and collections (null/omitted = full
        access, the root shape). `expires_at` is an ISO-8601 datetime string; omit for a key
        that never expires.
        """
        scope = KeyPermissions.model_validate(permissions) if permissions is not None else None
        expiry = datetime.fromisoformat(expires_at) if expires_at is not None else None
        created = await sdk.auth.create_key(name, permissions=scope, expires_at=expiry)
        return created.model_dump(mode="json")

    @mcp.tool()
    async def list_api_keys() -> Any:
        """
        List every API key — shows prefixes and metadata, never the plaintext key or hash.

        Includes both active and revoked keys so the full audit trail is visible.
        """
        keys = await sdk.auth.list_keys()
        return [key.model_dump(mode="json") for key in keys]

    @mcp.tool()
    async def revoke_api_key(key_id: str) -> Any:
        """Soft-revoke an API key (idempotent — the record remains for audit)."""
        await sdk.auth.revoke_key(key_id)
        return {}

    @mcp.tool()
    async def rotate_api_key(
        key_id: str,
        name: str | None = None,
        permissions: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> Any:
        """
        Rotate an API key: issue a fresh secret (optionally re-scoped) and revoke the old one.

        IMPORTANT: the replacement plaintext key is returned EXACTLY ONCE in the response.
        Omit `name` / `permissions` / `expires_at` to keep the source key's current value;
        `permissions` and `expires_at` use the same shape as `create_api_key`.
        """
        new_name: str | EllipsisType = name if name is not None else ...
        scope: KeyPermissions | None | EllipsisType = (
            KeyPermissions.model_validate(permissions) if permissions is not None else ...
        )
        expiry: datetime | None | EllipsisType = (
            datetime.fromisoformat(expires_at) if expires_at is not None else ...
        )
        rotated = await sdk.auth.rotate_key(
            key_id, name=new_name, permissions=scope, expires_at=expiry
        )
        return rotated.model_dump(mode="json")

    @mcp.tool()
    async def whoami() -> Any:
        """Report THIS token's capabilities + collection scope — what it is allowed to do."""
        return (await sdk.auth.whoami()).model_dump(mode="json")
