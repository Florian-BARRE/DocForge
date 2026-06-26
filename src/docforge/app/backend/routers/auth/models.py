# ====== Code Summary ======
# Request/response models for the auth router (login, me, API-key management).
# Secrets follow a strict shape: passwords are write-only inputs, the plaintext API key is returned
# exactly once on creation and never again, and listings expose only safe prefixes.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Body for POST /auth/login."""

    username: str = Field(..., min_length=1, description="Login handle.")
    password: str = Field(..., min_length=1, description="Plaintext password (never stored).")


class UserSummary(BaseModel):
    """A compact view of a user, safe to return to clients (no password hash)."""

    id: uuid.UUID = Field(..., description="User id.")
    username: str = Field(..., description="Login handle.")
    role: str = Field(..., description="Global role: 'root' | 'user'.")
    is_active: bool = Field(default=True, description="Whether the account can authenticate.")

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Response for POST /auth/login — a bearer access token + the authenticated user."""

    access_token: str = Field(..., description="Signed JWT access token (send as 'Bearer <token>').")
    token_type: str = Field(default="bearer", description="Token scheme — always 'bearer'.")
    user: UserSummary = Field(..., description="The authenticated user.")


class CollectionGrantSummary(BaseModel):
    """One per-collection grant held by the current user."""

    collection_id: uuid.UUID = Field(..., description="Collection the grant applies to.")
    role: str = Field(..., description="Per-collection role: 'read' | 'write' | 'admin'.")


class MeResponse(BaseModel):
    """Response for GET /auth/me — the caller's identity + their collection grants."""

    user: UserSummary = Field(..., description="The authenticated user.")
    grants: list[CollectionGrantSummary] = Field(
        default_factory=list,
        description="Per-collection grants. Empty for root (root has implicit admin everywhere).",
    )
    impersonated_by: uuid.UUID | None = Field(
        default=None,
        description=(
            "Set when the session was minted by a root impersonating this user — the impersonating "
            "root's id. None for an ordinary session. The UI uses it to show an 'Acting as' banner."
        ),
    )


class ApiKeyCreateRequest(BaseModel):
    """Body for POST /auth/keys — create a new API key for the current user."""

    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label.")


class ApiKeyCreatedResponse(BaseModel):
    """
    Response for POST /auth/keys.

    The ``key`` plaintext is shown EXACTLY ONCE here and is never retrievable again — only its
    hash is stored. Clients must capture it now.
    """

    id: uuid.UUID = Field(..., description="API key id.")
    name: str = Field(..., description="Human-readable label.")
    prefix: str = Field(..., description="First characters of the key, safe to display.")
    key: str = Field(..., description="The plaintext key — shown ONCE; store it now.")
    created_at: datetime = Field(..., description="Creation timestamp.")


class ApiKeySummary(BaseModel):
    """A stored API key as listed back to its owner — never includes the hash or plaintext."""

    id: uuid.UUID = Field(..., description="API key id.")
    name: str = Field(..., description="Human-readable label.")
    prefix: str = Field(..., description="First characters of the key, safe to display.")
    created_at: datetime = Field(..., description="Creation timestamp.")
    last_used_at: datetime | None = Field(default=None, description="Last successful use, if any.")
    revoked_at: datetime | None = Field(default=None, description="Revocation time, if revoked.")

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    """Response for GET /auth/keys — the current user's keys (prefixes only)."""

    keys: list[ApiKeySummary] = Field(default_factory=list, description="The user's API keys.")
    total: int = Field(..., description="Number of keys returned.")


class ApiKeyRevokeResponse(BaseModel):
    """Response for DELETE /auth/keys/{key_id}."""

    revoked: bool = Field(..., description="True if a previously-active key was revoked.")
    id: uuid.UUID = Field(..., description="The targeted key id.")
