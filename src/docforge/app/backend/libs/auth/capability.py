# ====== Code Summary ======
# The `Capability` enum — the coarse action classes an endpoint demands of the calling key. Reading is
# split in two usage profiles: READ_TEXT (the business surface a chatbot agent needs — documents,
# linearized views, outline, lean chunks, describe, the lean collection contract, job status) and
# READ_TECHNICAL (the internals surface — IR, pages, provenance, pipeline/search blobs, traces,
# payloads, raw blobs, exports, ops aggregates, the pipeline design routes, audit). The historical
# READ value survives ONLY as a legacy input alias: a stored or submitted `read` is normalized to
# BOTH halves on load (see KeyPermissions), so pre-split keys keep their full read surface with no
# data migration. No route ever requires READ.

# ====== Standard Library Imports ======
from enum import StrEnum


class Capability(StrEnum):
    """A coarse action class an endpoint requires of the calling key."""

    # Legacy pre-split alias — normalized to READ_TEXT + READ_TECHNICAL on load, never stored anew.
    READ = "read"
    READ_TEXT = "read_text"
    READ_TECHNICAL = "read_technical"
    WRITE = "write"
    SEARCH = "search"
    # CREATE gates collection creation specifically. A scoped key that holds it gains ownership of
    # what it creates: the new collection's id is appended to its own `collections` scope, so a key
    # need not know ids up front to be given "may create + full power over what it creates".
    CREATE = "create"
    ADMIN = "admin"


# What the legacy READ alias expands to.
LEGACY_READ_EXPANSION: tuple[Capability, ...] = (Capability.READ_TEXT, Capability.READ_TECHNICAL)

# Every capability a key can actually hold (the legacy alias excluded) — root's effective grant set.
CANONICAL_CAPABILITIES: tuple[Capability, ...] = tuple(
    capability for capability in Capability if capability is not Capability.READ
)


__all__ = ["Capability", "LEGACY_READ_EXPANSION", "CANONICAL_CAPABILITIES"]
