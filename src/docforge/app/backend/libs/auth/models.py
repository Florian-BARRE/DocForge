# ====== Code Summary ======
# The Principal value object — the authenticated identity attached to a request after credential
# resolution. Immutable and free of any DB session, so it can travel freely through dependencies
# and route handlers. Carries just enough to drive authorization (id + global role).

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

    Produced by ``AuthService.resolve_principal`` (from a JWT, a DB API key, or the static root
    key) or synthesized when auth is disabled. Immutable so it can be cached/passed around safely.

    Attributes:
        user_id (uuid.UUID): The backing user's id.
        username (str): The user's login handle (for logging / display).
        global_role (UserRole): The global role (root | user).
        is_root (bool): Convenience flag — True iff ``global_role`` is root.
        impersonated_by (uuid.UUID | None): When this identity was produced by a root
            impersonation token, the id of the root that minted it (audit/display only).
            None for an ordinary principal. This field NEVER widens what the principal may
            do — authorization is driven exclusively by ``global_role`` / per-collection grants.
    """

    user_id: uuid.UUID
    username: str
    global_role: UserRole
    is_root: bool
    impersonated_by: uuid.UUID | None = None

    @classmethod
    def from_user(
        cls,
        *,
        user_id: uuid.UUID,
        username: str,
        role: str,
        impersonated_by: uuid.UUID | None = None,
    ) -> "Principal":
        """
        Build a Principal from a user's stored fields.

        Args:
            user_id (uuid.UUID): The user's id.
            username (str): The user's login handle.
            role (str): The stored global role string (a ``UserRole`` value).
            impersonated_by (uuid.UUID | None): The id of the root impersonating this user, if any.

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
            impersonated_by=impersonated_by,
        )
