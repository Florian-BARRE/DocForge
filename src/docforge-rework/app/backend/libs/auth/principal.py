# ====== Code Summary ======
# AuthPrincipal — the authenticated identity handed to route handlers. It carries the resolved
# API key and its owning user, plus a derived `is_full_access` flag (a key with NULL permissions
# grants everything). When auth is DISABLED a synthetic full-access root principal is produced, so
# every endpoint sees a principal uniformly regardless of the AUTH_ENABLED toggle.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import ApiKey, AppUser


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    """
    The authenticated caller — the API key, its owning user, and the access scope.

    Attributes:
        user (AppUser | None): The owning account, or None for the synthetic dev principal.
        key (ApiKey | None): The authenticating key, or None for the synthetic dev principal.
        is_full_access (bool): True when the key's permissions are NULL (unscoped full access).
    """

    user: AppUser | None
    key: ApiKey | None
    is_full_access: bool

    @classmethod
    def synthetic_root(cls) -> AuthPrincipal:
        """
        Build the synthetic full-access principal used when authentication is disabled.

        Returns:
            AuthPrincipal: A principal with no backing rows and unscoped access.
        """
        # 1. No DB rows exist in dev mode — grant full access so endpoints behave uniformly.
        return cls(user=None, key=None, is_full_access=True)

    @classmethod
    def from_key(cls, key: ApiKey, user: AppUser) -> AuthPrincipal:
        """
        Build a principal from a verified key and its owning user.

        Args:
            key (ApiKey): The authenticated (non-revoked) API key.
            user (AppUser): The active account owning the key.

        Returns:
            AuthPrincipal: The identity, full-access when the key has no per-scope permissions.
        """
        # 1. NULL permissions means unscoped; per-scope enforcement is Lot 2.
        return cls(user=user, key=key, is_full_access=key.permissions is None)


__all__ = ["AuthPrincipal"]
