# ====== Code Summary ======
# Pydantic models for the keys-management router. The plaintext key appears in exactly one place —
# CreatedKey.key, returned once on creation. No model ever exposes the stored hash.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ...libs.auth import KeyPermissions


class CreateKeyRequest(BaseModel):
    """Body of a create-key request."""

    name: str = Field(min_length=1, description="Human-readable label for the key.")
    permissions: KeyPermissions | None = Field(
        default=None,
        description="Per-key capability + collection scope; null = full access (root).",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="Absolute expiry instant; null = never expires.",
    )


class RotateKeyRequest(BaseModel):
    """
    Body of a rotate-key request — every field optional so absence clones from the source key.

    Because ``None`` is BOTH the default AND a meaningful value (permissions=null → full access,
    expires_at=null → never expires), the handler distinguishes "field provided" from "field absent"
    via ``model_fields_set``; a field left out is copied verbatim from the key being rotated.

    Attributes:
        name (str | None): New label; absent = keep the source key's name.
        permissions (KeyPermissions | None): New scope; absent = keep the source blob, null = full
            access.
        expires_at (datetime | None): New expiry; absent = keep the source expiry, null = never
            expires.
    """

    name: str | None = Field(
        default=None, min_length=1, description="New label; absent = keep the source name."
    )
    permissions: KeyPermissions | None = Field(
        default=None,
        description="New scope; absent = keep the source blob, null = full access.",
    )
    expires_at: datetime | None = Field(
        default=None,
        description="New expiry instant; absent = keep the source expiry, null = never expires.",
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
        expires_at (datetime | None): The absolute expiry instant; null = never expires.
        key (str): The plaintext key — shown ONCE here, never stored or returned again.
    """

    id: str = Field(description="The key row's UUID.")
    name: str = Field(description="The label given at creation.")
    prefix: str = Field(description="The stored display prefix.")
    permissions: dict[str, Any] | None = Field(
        default=None, description="Per-scope blob; null = full access."
    )
    created_at: datetime = Field(description="When the key was created.")
    expires_at: datetime | None = Field(
        default=None, description="Absolute expiry instant; null = never expires."
    )
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
    expires_at: datetime | None = Field(
        default=None, description="Absolute expiry instant; null = never expires."
    )
    last_used_at: datetime | None = Field(
        default=None, description="Last successful authentication instant; null = never used."
    )
    revoked_at: datetime | None = Field(
        default=None, description="Soft-revocation timestamp; null when the key is active."
    )


__all__ = ["CreateKeyRequest", "RotateKeyRequest", "CreatedKey", "KeyInfo"]
