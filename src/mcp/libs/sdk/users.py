# ====== Code Summary ======
# Users sub-API: create / list / deactivate users and reset passwords (root only).
# Mirrors the backend's users router mounted at /api/v1/users.
# All routes require root privileges — the transport must carry a root-level API token.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any, Literal

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class UsersApi(LoggerClass):
    """
    Root-only user management endpoints.

    Wraps ``/api/v1/users`` and exposes create, list, deactivate, and password-reset
    as typed async methods. Every call requires the bearer token to belong to a root user.
    """

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def create(
        self,
        username: str,
        password: str,
        role: Literal["root", "user"] = "user",
    ) -> Any:
        """
        Create a new application user (root only).

        The password is argon2-hashed before storage; a duplicate username is rejected
        with HTTP 409 by the backend.

        Args:
            username (str): Unique login handle (1-255 chars).
            password (str): Initial plaintext password (hashed server-side, never stored).
            role (str): Global role to assign — ``"root"`` or ``"user"`` (default ``"user"``).

        Returns:
            Any: UserResponse — id, username, role, is_active, created_at.
        """
        # 1. POST the create request with the three required fields
        return await self._t.post("/users", {"username": username, "password": password, "role": role})

    async def list(self) -> Any:
        """
        List all application users, newest first (root only).

        Returns:
            Any: UserListResponse — list of UserResponse + total count.
        """
        # 1. GET all users from the root-gated endpoint
        return await self._t.get("/users")

    async def deactivate(self, user_id: str) -> Any:
        """
        Soft-deactivate a user account (root only).

        Deactivation blocks future authentication but preserves the user's API keys and
        collection grants for audit. Root cannot deactivate its own account (409 from
        the backend — self-lockout protection).

        Args:
            user_id (str): UUID of the user to deactivate.

        Returns:
            Any: DeactivateUserResponse — deactivated (bool) + id.
        """
        # 1. DELETE (soft) the user account
        return await self._t.delete(f"/users/{user_id}")

    async def reset_password(self, user_id: str, password: str) -> Any:
        """
        Reset a user's password (root only).

        The new password is argon2-hashed before storage; the plaintext is never logged
        or persisted. Returns 404 if the user does not exist.

        Args:
            user_id (str): UUID of the target user.
            password (str): New plaintext password (hashed server-side).

        Returns:
            Any: UserResponse — updated user record (no hash).
        """
        # 1. PUT the new password to the user's password sub-resource
        return await self._t.put(f"/users/{user_id}/password", {"password": password})
