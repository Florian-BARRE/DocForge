# ====== Code Summary ======
# CollectionAliasName — the pure grammar of a collection alias name and of the `alias:<name>` key-scope
# entry. One slug pattern (shared with the DB CHECK constraint), plus the names an alias may never take:
# a UUID-shaped string (it would be read as a collection id by the ref resolver) and the literal
# `/collections/<segment>` routes it would shadow (`contract-schema`, `import`).

# ====== Standard Library Imports ======
import re
import uuid

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.tables import COLLECTION_ALIAS_PATTERN

# The key-scope prefix naming an alias instead of a collection UUID: "alias:<name>".
ALIAS_SCOPE_PREFIX = "alias:"

# Literal /collections/<segment> routes an alias name would be shadowed by (or shadow).
_RESERVED_NAMES: frozenset[str] = frozenset({"contract-schema", "import"})

_PATTERN = re.compile(COLLECTION_ALIAS_PATTERN)


class CollectionAliasName:
    """Static helpers validating alias names and parsing ``alias:<name>`` scope entries."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionAliasName is a static-only class and cannot be instantiated.")

    @staticmethod
    def problem(name: str) -> str | None:
        """
        Explain why ``name`` is not a valid alias name.

        Args:
            name (str): The candidate alias name.

        Returns:
            str | None: A client-facing reason, or None when the name is valid.
        """
        # 1. The slug grammar (lowercase, digits, '-', '_', 1-63 chars, no leading separator).
        if not _PATTERN.fullmatch(name):
            return (
                f"alias name '{name}' must match {COLLECTION_ALIAS_PATTERN} (lowercase letters, "
                f"digits, '-' and '_', 1-63 chars)."
            )
        # 2. A UUID-shaped name would be read as a collection id, never as the alias.
        try:
            uuid.UUID(name)
            return f"alias name '{name}' looks like a collection UUID."
        except ValueError:
            pass
        # 3. Literal sub-routes of /collections cannot double as an alias.
        if name in _RESERVED_NAMES:
            return f"alias name '{name}' is reserved."
        return None

    @staticmethod
    def from_scope_entry(entry: str) -> str | None:
        """Return the alias name of an ``alias:<name>`` scope entry, or None for any other entry."""
        if entry.startswith(ALIAS_SCOPE_PREFIX):
            return entry[len(ALIAS_SCOPE_PREFIX) :]
        return None


__all__ = ["ALIAS_SCOPE_PREFIX", "CollectionAliasName"]
