# ====== Code Summary ======
# The Principal value object — the authenticated identity attached to a request after credential
# resolution. Immutable and free of any DB session, so it can travel freely through dependencies
# and route handlers. Carries just enough to drive authorization: the identity + the API-key
# permission scope (None = full access; a dict = a per-collection capability scope).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from dataclasses import dataclass

# ====== Internal Project Imports ======
from common_libs.storage.postgres.models import UserRole


@dataclass(frozen=True, slots=True)
class Principal:
    """
    The authenticated identity for a single request.

    Produced by ``AuthService.resolve_principal`` (from a password JWT, the static root key, or a
    DB API key) or synthesized when auth is disabled. Immutable so it can be passed around safely.

    The ``permissions`` field is the authorization pivot of the keys-only model:
      - ``None`` → FULL access (the root password-JWT login, the static root env API key, or a
        legacy DB key whose ``permissions`` column is NULL — kept full for backward compatibility).
      - a ``dict`` → a SCOPED API key; access is allowed only for the capabilities its entries
        grant on the path's collection (see ``backend.libs.auth.capabilities``).

    Attributes:
        user_id (uuid.UUID): The backing user's id (always the single root account).
        username (str): The user's login handle (for logging / display).
        global_role (UserRole): The global role (always root in the keys-only model).
        is_root (bool): Convenience flag — True iff ``global_role`` is root.
        permissions (dict | None): The API-key permission scope, or None for full access.
    """

    user_id: uuid.UUID
    username: str
    global_role: UserRole
    is_root: bool
    permissions: dict | None = None

    @property
    def has_full_access(self) -> bool:
        """
        Whether this principal bypasses per-capability checks.

        Returns:
            bool: True when ``permissions`` is None (root login, static root key, or a legacy
            null-permission key) — such a principal is allowed every capability on every collection.
        """
        # 1. A None scope is the single, explicit marker of unscoped (full) access
        return self.permissions is None

    @classmethod
    def from_user(
        cls,
        *,
        user_id: uuid.UUID,
        username: str,
        role: str,
        permissions: dict | None = None,
    ) -> "Principal":
        """
        Build a Principal from a user's stored fields.

        Args:
            user_id (uuid.UUID): The user's id.
            username (str): The user's login handle.
            role (str): The stored global role string (a ``UserRole`` value).
            permissions (dict | None): The API-key permission scope (None = full access).

        Returns:
            Principal: The corresponding immutable principal.
        """
        # 1. Normalize the stored string into the enum and derive the root flag
        global_role = UserRole(role)
        return cls(
            user_id=user_id,
            username=username,
            global_role=global_role,
            is_root=global_role is UserRole.ROOT,
            permissions=permissions,
        )
