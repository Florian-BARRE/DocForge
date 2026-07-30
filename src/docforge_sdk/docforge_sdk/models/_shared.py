# ====== Code Summary ======
# Vocabulary shared across resources, mirrored from the DocForge backend (never imported from it, to
# keep the SDK standalone). Holds the authorization enum and the per-key permission scope. Additional
# shared enums land here as later resource slices are added.

# ====== Standard Library Imports ======
from enum import StrEnum

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class Capability(StrEnum):
    """A coarse action class an endpoint requires of the calling key."""

    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    ADMIN = "admin"


class KeyPermissions(BaseModel):
    """
    The per-key permission scope stored on an API key.

    A key with ``null`` permissions is full access (root) and is represented as ``None`` at the call
    site, never as an instance of this model — this model always describes a SCOPED key.

    Attributes:
        capabilities (list[Capability]): The action classes the key grants (an empty list = a key
            that can authenticate but is authorized for nothing).
        collections (list[str]): Either ``["*"]`` (every collection) or an explicit list of
            collection UUID strings the key is scoped to.
    """

    capabilities: list[Capability] = Field(
        description="The action classes this key grants (READ / WRITE / SEARCH / ADMIN)."
    )
    collections: list[str] = Field(
        description="Collection scope: ['*'] for all, else explicit collection UUID strings."
    )


__all__ = ["Capability", "KeyPermissions"]
