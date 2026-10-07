# ====== Code Summary ======
# The per-key permission scope for scoped API keys. A `KeyPermissions` is the parsed, validated shape
# stored in the key's JSONB `permissions` column: the capabilities the key grants (see capability.py),
# the collections it is scoped to (`["*"]` = all, else explicit collection UUID strings and/or
# `alias:<name>` collection-alias entries, resolved per request to the alias's CURRENT target) and, for
# display, the named profile it was created from. Parsing normalizes two input shorthands into the
# canonical explicit list: a `profile` with no capabilities expands to its preset, and the legacy
# pre-split `read` expands to `read_text` + `read_technical` (so stored pre-split keys keep their
# whole read surface with NO data migration). A NULL column (None) is NOT modelled here — it means
# unscoped full access and is handled upstream on the principal.

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ====== Local Project Imports ======
from ..collection_ref.alias_name import CollectionAliasName
from .capability import LEGACY_READ_EXPANSION, Capability
from .profiles import KeyProfile, KeyProfiles

# The wildcard sentinel that scopes a key to every collection.
_ALL_COLLECTIONS = "*"


class KeyPermissions(BaseModel):
    """
    The parsed per-key permission scope stored in the ``api_key.permissions`` JSONB column.

    A key with NULL permissions is full access (root) and never reaches this model — it is short
    circuited on the principal. This model therefore always describes a SCOPED key.

    Attributes:
        capabilities (list[Capability]): The action classes the key grants (an empty list = a key
            that can authenticate but is authorized for nothing). Always the explicit, normalized
            list once parsed — never the legacy ``read`` alias.
        collections (list[str]): Either ``["*"]`` (every collection) or an explicit list of
            collection UUID strings and/or ``alias:<name>`` collection-alias entries.
        profile (KeyProfile | None): The named preset the key was created from (display only; the
            capabilities above are authoritative).
    """

    model_config = ConfigDict(extra="forbid")

    capabilities: list[Capability] = Field(
        default_factory=list,
        description="The action classes this key grants (read_text / read_technical / write / "
        "search / create / admin; the legacy 'read' = read_text + read_technical). May be omitted "
        "when 'profile' is given.",
    )
    collections: list[str] = Field(
        description="Collection scope: ['*'] for all, else explicit collection UUID strings and/or "
        "'alias:<name>' collection-alias entries (an alias entry follows the alias's CURRENT target, "
        "so re-pointing the alias re-scopes the key with no key edit; a deleted alias grants nothing)."
    )
    profile: KeyProfile | None = Field(
        default=None,
        description="Named capability preset (agent_reader / agent_searcher / operator / admin). "
        "Given instead of 'capabilities', it expands to the preset; stored for display only.",
    )

    @model_validator(mode="before")
    @classmethod
    def _expand_profile(cls, data: Any) -> Any:
        """
        Expand a ``profile`` given without capabilities into its preset, and require one of the two.

        Args:
            data (Any): The raw input (a dict for every real caller).

        Returns:
            Any: The input with ``capabilities`` filled from the profile when it was absent/empty.

        Raises:
            ValueError: When neither ``capabilities`` nor ``profile`` is provided.
        """
        # 1. Only dict inputs carry the shorthand; anything else is left to field validation.
        if not isinstance(data, dict):
            return data
        if "capabilities" not in data and data.get("profile") is None:
            raise ValueError("permissions need 'capabilities' or a 'profile'.")

        # 2. A known profile with no explicit capabilities expands to its preset (an unknown profile
        #    is left for the field validator to reject with a precise enum error).
        profile = data.get("profile")
        if profile is not None and not data.get("capabilities") and profile in set(KeyProfile):
            return {**data, "capabilities": KeyProfiles.capabilities_of(KeyProfile(profile))}
        return data

    @field_validator("capabilities")
    @classmethod
    def _normalize_capabilities(cls, value: list[Capability]) -> list[Capability]:
        """
        Expand the legacy ``read`` alias into both read halves and drop duplicates (order kept).

        Args:
            value (list[Capability]): The declared capabilities.

        Returns:
            list[Capability]: The canonical capability list, free of the legacy alias.
        """
        # 1. Expand the alias in place, then de-duplicate while preserving declaration order.
        expanded: list[Capability] = []
        for capability in value:
            expanded.extend(
                LEGACY_READ_EXPANSION if capability is Capability.READ else (capability,)
            )
        return list(dict.fromkeys(expanded))

    @model_validator(mode="after")
    def _check_profile_consistency(self) -> KeyPermissions:
        """
        Reject a profile label that contradicts the explicit capabilities it travels with.

        Returns:
            KeyPermissions: The validated model, unchanged.

        Raises:
            ValueError: When both are given and the capabilities differ from the profile's preset.
        """
        # 1. The label is display-only — it must never misdescribe the authoritative capabilities.
        if self.profile is not None and set(self.capabilities) != set(
            KeyProfiles.capabilities_of(self.profile)
        ):
            raise ValueError(f"capabilities contradict profile '{self.profile}'.")
        return self

    @field_validator("collections")
    @classmethod
    def _validate_collections(cls, value: list[str]) -> list[str]:
        """
        Enforce the collection-scope shape: a pure wildcard, or UUID strings / ``alias:<name>`` entries.

        Args:
            value (list[str]): The declared collection scope.

        Returns:
            list[str]: The validated scope, unchanged.

        Raises:
            ValueError: If the wildcard is mixed with explicit ids, or an entry is neither a UUID nor
                a well-formed alias entry (alias EXISTENCE is checked at key write, not here).
        """
        # 1. The wildcard is all-or-nothing — mixing it with explicit ids is ambiguous.
        if _ALL_COLLECTIONS in value:
            if value != [_ALL_COLLECTIONS]:
                raise ValueError("collections wildcard '*' cannot be combined with explicit ids.")
            return value

        # 2. Every explicit entry is a collection UUID or an ``alias:<name>`` with a valid alias name.
        for entry in value:
            alias = CollectionAliasName.from_scope_entry(entry)
            if alias is not None:
                problem = CollectionAliasName.problem(alias)
                if problem is not None:
                    raise ValueError(f"collection scope entry '{entry}': {problem}")
                continue
            try:
                uuid.UUID(entry)
            except (ValueError, AttributeError, TypeError):
                raise ValueError(
                    f"collection scope entry '{entry}' is neither a collection UUID nor "
                    f"'alias:<name>'."
                )
        return value

    def alias_names(self) -> list[str]:
        """
        Return the collection-alias names this scope names through ``alias:<name>`` entries.

        Returns:
            list[str]: The alias names, in declaration order (empty for a UUID-only/wildcard scope).
        """
        # 1. Keep only the alias entries, stripped of their prefix.
        names = (CollectionAliasName.from_scope_entry(entry) for entry in self.collections)
        return [name for name in names if name is not None]

    def with_resolved_aliases(self, targets: Mapping[str, str]) -> KeyPermissions:
        """
        Return the EFFECTIVE scope: each ``alias:<name>`` entry replaced by its current target id.

        An alias absent from ``targets`` (deleted since the key was written) is DROPPED — it grants
        nothing (fail closed). A scope left with no entry then covers no collection at all.

        Args:
            targets (Mapping[str, str]): Alias name → current target collection id (per request).

        Returns:
            KeyPermissions: A copy whose ``collections`` lists only collection ids (or the wildcard).
        """
        # 1. Nothing to do for a scope with no alias entry (the common case).
        if not self.alias_names():
            return self

        # 2. Substitute each alias with its live target; a dangling alias contributes nothing.
        effective: list[str] = []
        for entry in self.collections:
            alias = CollectionAliasName.from_scope_entry(entry)
            if alias is None:
                effective.append(entry)
            elif alias in targets:
                effective.append(targets[alias])
        return self.model_copy(update={"collections": list(dict.fromkeys(effective))})

    def to_stored(self) -> dict[str, Any]:
        """
        Serialize this scope into the JSONB blob persisted on the key row.

        The blob always carries the explicit, normalized capability list; the ``profile`` label is
        written only when set, so a profile-less key keeps the exact pre-profile blob shape.

        Returns:
            dict[str, Any]: The JSON-safe permissions blob.
        """
        # 1. JSON mode keeps enum members as their string values; a null profile is left out.
        return self.model_dump(mode="json", exclude_none=True)

    def grants_capability(self, capability: Capability) -> bool:
        """
        Tell whether this scope grants the given capability.

        Args:
            capability (Capability): The capability the endpoint demands.

        Returns:
            bool: True when the capability is present in this key's grants.
        """
        # 1. The legacy READ demand is satisfied only by holding BOTH read halves.
        if capability is Capability.READ:
            return all(half in self.capabilities for half in LEGACY_READ_EXPANSION)

        # 2. A scoped key grants only the capabilities explicitly listed.
        return capability in self.capabilities

    def grants_collection(self, collection_id: str) -> bool:
        """
        Tell whether this scope covers the given collection.

        Args:
            collection_id (str): The target collection id taken from the request path.

        Returns:
            bool: True when the key is wildcard-scoped or explicitly lists the collection.
        """
        # 1. Wildcard covers everything; otherwise the id must be explicitly enumerated.
        return _ALL_COLLECTIONS in self.collections or collection_id in self.collections

    def scoped_collection_ids(self) -> set[str] | None:
        """
        Return the explicit collection ids this key may see, or None when wildcard-scoped.

        A ``None`` result means "every collection" (the wildcard), letting a caller treat a
        wildcard key the same as full access. An explicit scope returns exactly its id set.

        Returns:
            set[str] | None: The scoped collection ids, or None for wildcard (all) scope.
        """
        # 1. Wildcard = unrestricted; otherwise the exact enumerated set.
        if _ALL_COLLECTIONS in self.collections:
            return None
        return set(self.collections)


__all__ = ["Capability", "KeyPermissions", "KeyProfile"]
