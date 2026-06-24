# ====== Code Summary ======
# Request/response models for the per-collection collaborators sub-resource (access grants).
# Mirrors the GitHub-collaborator model: list grants, set a user's role, revoke a user's grant.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class AccessGrantResponse(BaseModel):
    """One collaborator's grant on a collection."""

    user_id: uuid.UUID = Field(..., description="Grantee user id.")
    username: str | None = Field(default=None, description="Grantee login handle, if resolvable.")
    role: str = Field(..., description="Per-collection role: 'read' | 'write' | 'admin'.")
    granted_by: uuid.UUID | None = Field(default=None, description="Who granted it (audit).")
    created_at: datetime = Field(..., description="When the grant was created.")


class AccessListResponse(BaseModel):
    """Response for GET /collections/{id}/access — the collection's collaborators."""

    collection_id: uuid.UUID = Field(..., description="The collection.")
    grants: list[AccessGrantResponse] = Field(default_factory=list, description="Collaborators.")
    total: int = Field(..., description="Number of grants returned.")


class SetAccessRequest(BaseModel):
    """Body for PUT /collections/{id}/access/{user_id} — set a user's role on the collection."""

    role: Literal["read", "write", "admin"] = Field(
        ..., description="Per-collection role to grant."
    )


class RevokeAccessResponse(BaseModel):
    """Response for DELETE /collections/{id}/access/{user_id}."""

    revoked: bool = Field(..., description="True if a grant was removed.")
    collection_id: uuid.UUID = Field(..., description="The collection.")
    user_id: uuid.UUID = Field(..., description="The user whose grant was revoked.")
