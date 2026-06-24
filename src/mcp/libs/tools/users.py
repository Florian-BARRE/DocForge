# ====== Code Summary ======
# MCP tools for user management: create / list / deactivate / reset password.
# All routes are root-only — the bearer token on the MCP server must belong to a root user.
# Thin wrappers over sdk.users — all path/body logic lives in libs/sdk/users.py.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from mcp.server.fastmcp import FastMCP

# ====== Local Project Imports ======
from ..sdk import DocForgeClient


def register(mcp: FastMCP, sdk: DocForgeClient) -> None:
    """
    Register user management tools on the MCP server.

    Args:
        mcp (FastMCP): The MCP server instance.
        sdk (DocForgeClient): The DocForge API client.
    """

    @mcp.tool()
    async def create_user(
        username: str,
        password: str,
        role: Literal["root", "user"] = "user",
    ) -> Any:
        """
        Create a new application user (root only).

        The password is argon2-hashed server-side before storage — the plaintext is never
        persisted or logged. A duplicate username is rejected with HTTP 409. Defaults to
        role='user'; pass role='root' to create another root administrator.
        """
        return await sdk.users.create(username, password, role)

    @mcp.tool()
    async def list_users() -> Any:
        """
        List all application users, newest first (root only).

        Returns id, username, role, is_active, and created_at for each user. The password
        hash is never included in any response.
        """
        return await sdk.users.list()

    @mcp.tool()
    async def deactivate_user(user_id: str) -> Any:
        """
        Soft-deactivate a user account (root only).

        Blocks future authentication for the account without deleting it — the user's API
        keys and collection grants are preserved for audit. Root cannot deactivate its own
        account (backend returns 409 — self-lockout protection).
        """
        return await sdk.users.deactivate(user_id)

    @mcp.tool()
    async def reset_user_password(user_id: str, password: str) -> Any:
        """
        Reset a user's password (root only).

        The new password is argon2-hashed server-side; the plaintext is never logged or
        persisted. Returns 404 if the user does not exist.
        """
        return await sdk.users.reset_password(user_id, password)
