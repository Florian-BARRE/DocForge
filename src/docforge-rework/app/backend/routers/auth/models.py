# ====== Code Summary ======
# Pydantic models for the keys-management router. The plaintext key appears in exactly one place —
# CreatedKey.key, returned once on creation. No model ever exposes the stored hash.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class CreateKeyRequest(BaseModel):
    """Body of a create-key request."""

    name: str = Field(description="Human-readable label for the key.")
    permissions: dict[str, Any] | None = Field(
        default=None,
        description="Per-scope permissions blob; null = full access (Lot 2 enforces scoping).",
    )


class CreatedKey(BaseModel):
    """
    The create-key response — the ONLY place the plaintext key is ever returned.

    Attributes:
        id (str): The key row's UUID.
        name (str): The label given at creation.
        prefix (str): The stored display prefix (safe to show; not a secret on its own).
        permissions (dict | None): The per-scope blob; null = full access.
        created_at (datetime): When the key was created.
        key (str): The plaintext key — shown ONCE here, never stored or returned again.
    """

    id: str = Field(description="The key row's UUID.")
    name: str = Field(description="The label given at creation.")
    prefix: str = Field(description="The stored display prefix.")
    permissions: dict[str, Any] | None = Field(
        default=None, description="Per-scope blob; null = full access."
    )
    created_at: datetime = Field(description="When the key was created.")
    key: str = Field(description="Plaintext key — shown ONCE, never recoverable afterwards.")


class KeyInfo(BaseModel):
    """A key as listed — metadata only, never the hash or the plaintext."""

    id: str = Field(description="The key row's UUID.")
    name: str = Field(description="The label given at creation.")
    prefix: str = Field(description="The stored display prefix.")
    permissions: dict[str, Any] | None = Field(
        default=None, description="Per-scope blob; null = full access."
    )
    created_at: datetime = Field(description="When the key was created.")
    revoked_at: datetime | None = Field(
        default=None, description="Soft-revocation timestamp; null when the key is active."
    )


__all__ = ["CreateKeyRequest", "CreatedKey", "KeyInfo"]
