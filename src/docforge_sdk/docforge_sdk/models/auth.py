# ====== Code Summary ======
# Request/response models for the auth (API-key management) resource, mirrored field-for-field from the
# DocForge backend router models. The response ``permissions`` field is the opaque JSONB blob the server
# stores, so it is typed as a plain dict rather than the structured KeyPermissions.

# ====== Standard Library Imports ======
from datetime import datetime
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from ._shared import KeyPermissions


class CreateKeyRequest(BaseModel):
    """
    Body of a create-key request.

    Attributes:
        name (str): Human-readable label for the key.
        permissions (KeyPermissions | None): Per-key capability + collection scope; ``None`` = full
            access (root).
        expires_at (datetime | None): Absolute expiry instant; ``None`` = never expires.
    """

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

    Serialization is CRUCIAL here: the backend distinguishes "field absent" (clone the source key's
    value) from "field present but null" (a meaningful value — ``permissions=null`` means full access,
    ``expires_at=null`` means never expires). Callers must therefore dump this model with
    ``exclude_unset=True`` so a field that was never set is omitted from the body, while an explicitly
    provided ``None`` is sent as JSON ``null``. The auth resource does this for you.

    Attributes:
        name (str | None): New label; absent = keep the source name.
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
    The create/rotate response — the ONLY place the plaintext key is ever returned.

    Attributes:
        id (str): The key row's UUID.
        name (str): The label given at creation.
        prefix (str): The stored display prefix (safe to show; not a secret on its own).
        permissions (dict[str, Any] | None): The opaque per-scope JSONB blob; ``None`` = full access.
        created_at (datetime): When the key was created.
        expires_at (datetime | None): The absolute expiry instant; ``None`` = never expires.
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
    """
    A key as listed — metadata only, never the hash or the plaintext.

    Attributes:
        id (str): The key row's UUID.
        name (str): The label given at creation.
        prefix (str): The stored display prefix.
        permissions (dict[str, Any] | None): The opaque per-scope JSONB blob; ``None`` = full access.
        created_at (datetime): When the key was created.
        expires_at (datetime | None): The absolute expiry instant; ``None`` = never expires.
        last_used_at (datetime | None): Last successful authentication instant; ``None`` = never used.
        revoked_at (datetime | None): Soft-revocation timestamp; ``None`` when the key is active.
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
    last_used_at: datetime | None = Field(
        default=None, description="Last successful authentication instant; null = never used."
    )
    revoked_at: datetime | None = Field(
        default=None, description="Soft-revocation timestamp; null when the key is active."
    )


__all__ = ["CreateKeyRequest", "RotateKeyRequest", "CreatedKey", "KeyInfo"]
