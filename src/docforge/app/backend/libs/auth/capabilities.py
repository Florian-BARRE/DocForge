# ====== Code Summary ======
# The capability taxonomy for API-key authorization — the SINGLE source of truth for what a key
# may do per collection. Defines the fine-grained capabilities, the read/write/admin shortcuts that
# expand into capability sets, and the helper that answers "does this key's permissions scope grant
# capability C on collection X?". The enforcement dependencies (dependencies.py) consume this; no
# authorization policy lives anywhere else.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# Wildcard collection id in a permission entry — an entry scoped to "*" applies to EVERY collection,
# including ones created after the key was minted.
WILDCARD_COLLECTION = "*"


class Capability(StrEnum):
    """
    A fine-grained, per-collection capability an API key can be granted.

    Each value is the wire string stored inside a key's ``permissions`` scope and tagged on the
    matching route by ``require_capability``. Dotted values group capabilities by resource so the
    UI can present them in families (documents.* / config.* / …).

    Attributes:
        DOCUMENTS_READ: List/get documents, files (original/pdf/markdown), pages, chunks(read).
        DOCUMENTS_WRITE: Ingest, update metadata, reingest, delete documents (and page reingest).
        SEARCH: Run collection / in-document search.
        CONFIG_READ: Read config state / schema / history.
        CONFIG_WRITE: Update / rollback config.
        CHUNKS_WRITE: Edit chunk text (and optionally re-embed it).
        COLLECTION_ADMIN: Delete the collection, manage its resource limits.
    """

    DOCUMENTS_READ = "documents.read"
    DOCUMENTS_WRITE = "documents.write"
    SEARCH = "search"
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"
    CHUNKS_WRITE = "chunks.write"
    COLLECTION_ADMIN = "collection.admin"


class PermissionRole(StrEnum):
    """
    A shortcut role chosen when scoping an API key to a collection.

    ``read`` / ``write`` / ``admin`` expand into fixed capability sets (the common cases);
    ``custom`` means the entry carries a hand-picked ``capabilities`` list instead.

    Attributes:
        READ: Expands to the read capability set.
        WRITE: Expands to the read set plus the write capabilities.
        ADMIN: Expands to the write set plus collection administration.
        CUSTOM: Use the entry's explicit ``capabilities`` list verbatim.
    """

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    CUSTOM = "custom"


# Role → capability-set expansion. Built once at import; each higher tier is a strict superset of
# the lower one (read ⊂ write ⊂ admin) so a "write" key implicitly reads, etc.
_READ_CAPS: frozenset[Capability] = frozenset(
    {Capability.DOCUMENTS_READ, Capability.SEARCH, Capability.CONFIG_READ}
)
_WRITE_CAPS: frozenset[Capability] = _READ_CAPS | {
    Capability.DOCUMENTS_WRITE,
    Capability.CONFIG_WRITE,
    Capability.CHUNKS_WRITE,
}
_ADMIN_CAPS: frozenset[Capability] = _WRITE_CAPS | {Capability.COLLECTION_ADMIN}

_ROLE_EXPANSION: dict[PermissionRole, frozenset[Capability]] = {
    PermissionRole.READ: _READ_CAPS,
    PermissionRole.WRITE: _WRITE_CAPS,
    PermissionRole.ADMIN: _ADMIN_CAPS,
}


class CapabilityHelpers:
    """
    Static-only helpers that interpret a key's ``permissions`` scope against the taxonomy.

    The ``permissions`` scope shape (stored on ``api_key.permissions``, JSONB):
        ``{"entries": [{"collection_id": "*"|"<uuid>", "role": "read"|"write"|"admin"|"custom",
                        "capabilities": ["documents.read", ...]}]}``
    A ``None`` scope means FULL access (root login, the static root env key, or a legacy/back-compat
    key created before scoping existed) — that short-circuit lives in the dependency, not here.
    """

    logger = loggerplusplus.bind(identifier="CapabilityHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CapabilityHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def expand_entry(cls, entry: dict) -> set[Capability]:
        """
        Compute the effective capability set granted by a single permission entry.

        Args:
            entry (dict): One ``permissions.entries`` item (``role`` + optional ``capabilities``).

        Returns:
            set[Capability]: The capabilities this entry grants. A ``custom`` role uses the entry's
            explicit ``capabilities`` list (unknown strings ignored); a known shortcut role expands
            to its fixed set; an unrecognized role grants nothing.
        """
        # 1. Resolve the shortcut role; an unparseable role grants nothing (fail closed)
        try:
            role = PermissionRole(str(entry.get("role")))
        except ValueError:
            return set()

        # 2. custom → use the explicit capability list (drop any value outside the taxonomy)
        if role is PermissionRole.CUSTOM:
            return {
                Capability(c)
                for c in entry.get("capabilities", []) or []
                if c in set(Capability)
            }

        # 3. read/write/admin → fixed expansion
        return set(_ROLE_EXPANSION[role])

    @classmethod
    def grants(cls, permissions: dict, collection_id: str, capability: Capability) -> bool:
        """
        Decide whether a scoped key's permissions grant ``capability`` on ``collection_id``.

        Args:
            permissions (dict): The key's ``permissions`` scope (the dict, never None here).
            collection_id (str): The path's collection id (stringified UUID).
            capability (Capability): The capability the route requires.

        Returns:
            bool: True iff some entry matches the collection (its exact id or the ``*`` wildcard)
            AND grants the required capability.
        """
        # 1. Scan entries for one that matches this collection and grants the capability
        for entry in permissions.get("entries", []) or []:
            entry_cid = str(entry.get("collection_id", ""))
            if entry_cid not in (collection_id, WILDCARD_COLLECTION):
                continue
            if capability in cls.expand_entry(entry):
                return True
        return False

    @classmethod
    def validate_permissions(cls, permissions: dict) -> None:
        """
        Validate a client-supplied ``permissions`` scope against the taxonomy.

        Args:
            permissions (dict): The scope to validate (``{"entries": [...]}``).

        Raises:
            ValueError: When the shape is malformed, a role is unknown, a custom entry carries no /
            invalid capabilities, or a non-custom entry is missing its collection id.
        """
        # 1. Top-level shape
        if not isinstance(permissions, dict):
            raise ValueError("permissions must be an object.")
        entries = permissions.get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("permissions.entries must be a non-empty list.")

        valid_caps = set(Capability)
        # 2. Per-entry validation
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError(f"permissions.entries[{idx}] must be an object.")

            # 2a. collection_id — a uuid or the wildcard
            cid = entry.get("collection_id")
            if not isinstance(cid, str) or not cid:
                raise ValueError(
                    f"permissions.entries[{idx}].collection_id must be a uuid or '*'."
                )

            # 2b. role — a known shortcut
            try:
                role = PermissionRole(str(entry.get("role")))
            except ValueError:
                raise ValueError(
                    f"permissions.entries[{idx}].role must be one of "
                    f"{[r.value for r in PermissionRole]}."
                )

            # 2c. custom → must carry a non-empty list of in-taxonomy capabilities
            if role is PermissionRole.CUSTOM:
                caps = entry.get("capabilities")
                if not isinstance(caps, list) or not caps:
                    raise ValueError(
                        f"permissions.entries[{idx}] role 'custom' requires a non-empty "
                        f"capabilities list."
                    )
                unknown = [c for c in caps if c not in valid_caps]
                if unknown:
                    raise ValueError(
                        f"permissions.entries[{idx}] has unknown capabilities {unknown}; "
                        f"allowed: {sorted(valid_caps)}."
                    )
