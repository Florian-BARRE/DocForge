# ====== Code Summary ======
# KeyGrantGuard — the anti-escalation rule of key management. A full-access caller (NULL-permission
# root key, or auth off) may mint / list / rotate / revoke any key. A SCOPED admin key may only act on
# keys whose scope is a SUBSET of its own: every capability it grants the caller holds, every collection
# it names the caller is scoped to, never NULL permissions (root-equivalent) and never the "*" wildcard
# unless the caller holds "*". An `alias:<name>` entry is only grantable by a caller whose own scope
# names that same alias (or "*"): an alias follows re-points the caller does not control, so its
# current target being in scope is not enough. Lives next to KeyScopeAliases (the other key-write
# scope rule) so create and rotate share both.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from pydantic import ValidationError

# ====== Local Project Imports ======
from .permissions import KeyPermissions
from .principal import AuthPrincipal

# The wildcard sentinel that scopes a key to every collection.
_ALL_COLLECTIONS = "*"


class KeyGrantGuard:
    """Static subset checks keeping a scoped admin from granting more than it holds."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("KeyGrantGuard is a static-only class and cannot be instantiated.")

    @staticmethod
    def __caller_scope(principal: AuthPrincipal) -> tuple[KeyPermissions, KeyPermissions]:
        """
        Parse the scoped caller's permissions: (as stored, with its aliases resolved).

        Raises:
            HTTPException: 403 when the caller's stored blob is malformed.
        """
        # 1. A malformed caller blob grants nothing (mirrors AuthzGuard).
        raw = principal.key.permissions if principal.key is not None else None
        try:
            stored = KeyPermissions.model_validate(raw)
        except ValidationError:
            raise HTTPException(status_code=403, detail="API key has malformed permissions.")
        return stored, stored.with_resolved_aliases(principal.alias_targets)

    @classmethod
    def _excess(cls, principal: AuthPrincipal, requested: KeyPermissions | None) -> str | None:
        """
        Explain what ``requested`` grants beyond the caller's own scope, or None when it is a subset.

        Args:
            principal (AuthPrincipal): The scoped (non-full-access) caller.
            requested (KeyPermissions | None): The scope to grant (None = full access).

        Returns:
            str | None: A client-facing reason, or None when the grant is allowed.
        """
        # 1. Full access (NULL permissions) is root-equivalent — never mintable by a scoped key.
        if requested is None:
            return "a scoped key cannot grant full access (permissions=null)."
        stored, effective = cls.__caller_scope(principal)

        # 2. Capabilities: every requested one must be held by the caller.
        missing = [c.value for c in requested.capabilities if c not in effective.capabilities]
        if missing:
            return f"cannot grant capabilities the caller lacks: {', '.join(missing)}."

        # 3. Collections: '*' only from a '*' caller; every other entry only as the caller STORES it
        #    (literal UUID or alias name). Never via the caller's RESOLVED aliases: an alias-only
        #    holder could otherwise pin the alias's current target as a UUID and keep access after
        #    the alias is re-pointed away from it (a blue/green cut-off would not cut it off).
        if _ALL_COLLECTIONS in stored.collections:
            return None
        if _ALL_COLLECTIONS in requested.collections:
            return "a collection-scoped key cannot grant the '*' collection wildcard."
        owned = {entry.lower() for entry in stored.collections}
        outside = [entry for entry in requested.collections if entry.lower() not in owned]
        if outside:
            return f"cannot grant collections outside the caller's scope: {', '.join(outside)}."
        return None

    @classmethod
    def assert_can_grant(cls, principal: AuthPrincipal, requested: KeyPermissions | None) -> None:
        """
        Refuse a key create / re-scope that would exceed the caller's own grant.

        Args:
            principal (AuthPrincipal): The caller.
            requested (KeyPermissions | None): The scope the new key would carry.

        Raises:
            HTTPException: 403 naming the excess.
        """
        # 1. Full access may grant anything; a scoped key only a subset of itself.
        if principal.is_full_access:
            return
        problem = cls._excess(principal, requested)
        if problem is not None:
            raise HTTPException(status_code=403, detail=f"Key grant refused: {problem}")

    @classmethod
    def can_manage(cls, principal: AuthPrincipal, stored_permissions: Any) -> bool:
        """
        Tell whether the caller may see / rotate / revoke a key with this STORED scope.

        Args:
            principal (AuthPrincipal): The caller.
            stored_permissions (Any): The target key's ``permissions`` JSONB (None = full access).

        Returns:
            bool: True for a full-access caller, or when the key's scope is a subset of the caller's
            (a malformed target blob is never manageable by a scoped caller).
        """
        # 1. Full access manages every key.
        if principal.is_full_access:
            return True
        # 2. A root-equivalent target, or one exceeding the caller's scope, is out of reach.
        if stored_permissions is None:
            return False
        try:
            target = KeyPermissions.model_validate(stored_permissions)
        except ValidationError:
            return False
        return cls._excess(principal, target) is None


__all__ = ["KeyGrantGuard"]
