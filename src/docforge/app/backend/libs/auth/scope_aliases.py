# ====== Code Summary ======
# KeyScopeAliases — the I/O side of `alias:<name>` key-scope entries. At authentication it resolves the
# aliases a key names to their CURRENT targets (one uncached query per request, only for keys that name
# an alias), so the key cache (AUTH_KEY_CACHE_TTL_SECONDS) only ever caches the alias NAME, never its
# target: a re-point is effective on the next request. At key write, `validate_scope_entries` is the
# single chokepoint checking a requested collection scope against the live store (today: every alias
# must exist); a dangling alias in an already-stored key is NOT an error there — it fails closed.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ..collection_ref.alias_name import CollectionAliasName
from .permissions import KeyPermissions


class KeyScopeAliases:
    """Static helpers resolving and validating the alias entries of a key's collection scope."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("KeyScopeAliases is a static-only class and cannot be instantiated.")

    @staticmethod
    def names_in(raw_permissions: Any) -> list[str]:
        """
        Read the alias names out of a STORED permissions blob, tolerating any malformed shape.

        Args:
            raw_permissions (Any): The ``api_key.permissions`` JSONB value (None = full access).

        Returns:
            list[str]: The alias names (empty when none, or when the blob is not a scoped dict — a
            malformed blob is denied later by the authZ gate, never here).
        """
        # 1. Only a dict with a list of string collections can carry alias entries.
        if not isinstance(raw_permissions, dict):
            return []
        collections = raw_permissions.get("collections")
        if not isinstance(collections, list):
            return []
        names = (
            CollectionAliasName.from_scope_entry(entry)
            for entry in collections
            if isinstance(entry, str)
        )
        return [name for name in names if name]

    @classmethod
    async def targets_for(cls, raw_permissions: Any) -> dict[str, str]:
        """
        Resolve the aliases a stored key names to their current target ids (per request, uncached).

        Args:
            raw_permissions (Any): The key's stored permissions blob.

        Returns:
            dict[str, str]: Alias name → target collection id; a deleted alias is simply absent.
        """
        # 1. The common case (no alias entry) costs no query.
        names = cls.names_in(raw_permissions)
        if not names:
            return {}
        targets = await CONTEXT.database.collection_aliases.targets_of(names)
        return {name: str(collection_id) for name, collection_id in targets.items()}

    @staticmethod
    async def validate_scope_entries(permissions: KeyPermissions | None) -> None:
        """
        Check a REQUESTED key scope against the live store before it is written (create/rotate).

        The shape (UUID / ``alias:<name>`` / ``*``) is already validated by ``KeyPermissions``; this
        adds the existence check of every named alias. Keep further scope-entry write rules here so
        every key write path shares them.

        Args:
            permissions (KeyPermissions | None): The requested scope (None = full access).

        Raises:
            HTTPException: 422 naming the alias(es) that do not exist.
        """
        # 1. Full access / no alias entry → nothing to look up.
        if permissions is None or not permissions.alias_names():
            return

        # 2. Every named alias must exist now (a later deletion fails closed instead).
        names = permissions.alias_names()
        known = await CONTEXT.database.collection_aliases.targets_of(names)
        unknown = sorted(name for name in set(names) if name not in known)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown collection alias(es) in the key scope: {', '.join(unknown)}.",
            )


__all__ = ["KeyScopeAliases"]
