# ====== Code Summary ======
# Request/response models for the root-only users router (create / list / deactivate /
# password reset). Passwords are write-only inputs; responses never carry the password hash.

# ====== Standard Library Imports ======
import uuid
from datetime import datetime
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Body for POST /users — create a new application user (root only)."""

    username: str = Field(..., min_length=1, max_length=255, description="Unique login handle.")
    password: str = Field(..., min_length=1, description="Initial plaintext password (hashed, never stored).")
    role: Literal["root", "user"] = Field(
        default="user", description="Global role to assign (defaults to 'user')."
    )


class UpdatePasswordRequest(BaseModel):
    """Body for PUT /users/{id}/password — reset a user's password (root only)."""

    password: str = Field(..., min_length=1, description="New plaintext password (hashed, never stored).")


class UserResponse(BaseModel):
    """A user resource as returned to root — never includes the password hash."""

    id: uuid.UUID = Field(..., description="User id.")
    username: str = Field(..., description="Login handle.")
    role: str = Field(..., description="Global role: 'root' | 'user'.")
    is_active: bool = Field(..., description="Whether the account can authenticate.")
    created_at: datetime = Field(..., description="Creation timestamp.")

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Response for GET /users."""

    users: list[UserResponse] = Field(default_factory=list, description="All users (newest first).")
    total: int = Field(..., description="Number of users returned.")


class DeactivateUserResponse(BaseModel):
    """Response for DELETE /users/{id} — soft deactivation acknowledgement."""

    deactivated: bool = Field(..., description="True if the account was deactivated.")
    id: uuid.UUID = Field(..., description="The targeted user id.")


class ImpersonateResponse(BaseModel):
    """
    Response for POST /users/{id}/impersonate — a login-shaped session for the target user.

    Mirrors the auth router's ``LoginResponse`` (access_token + token_type + user) so the frontend
    can swap the active session seamlessly. The token authenticates AS the target user; the embedded
    ``impersonated_by`` audit claim is surfaced separately via ``/auth/me``.
    """

    access_token: str = Field(..., description="Signed JWT for the target user (send as 'Bearer <token>').")
    token_type: str = Field(default="bearer", description="Token scheme — always 'bearer'.")
    user: UserResponse = Field(..., description="The impersonated (target) user.")
