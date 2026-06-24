# ====== Code Summary ======
# Root-only user management router: create / list / deactivate users + reset passwords.
# Every route is gated by require_root. Deletion is implemented as a soft deactivation so audit
# trails (keys, grants) survive; password hashing is delegated to AuthService's PasswordHelpers.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Principal, PasswordHelpers, require_root
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.users.models import (
    CreateUserRequest,
    DeactivateUserResponse,
    UpdatePasswordRequest,
    UserListResponse,
    UserResponse,
)

router = APIRouter(tags=["users"])


@router.post("", response_model=UserResponse, status_code=201)
@auto_handle_errors
async def create_user(
    body: CreateUserRequest, _root: Principal = Depends(require_root)
) -> UserResponse:
    """
    Create a new application user (root only).

    The password is hashed with argon2 before storage; a duplicate username is rejected with 409.
    """
    # 1. Hash the supplied password (plaintext never persisted/logged)
    password_hash = PasswordHelpers.hash(body.password)

    # 2. Persist the user; the unique username constraint surfaces a duplicate as 409
    try:
        async with CONTEXT.postgres.session() as session:
            user = await CONTEXT.user_repo.create(
                session, username=body.username, password_hash=password_hash, role=body.role
            )
            response = UserResponse.model_validate(user)
    except IntegrityError:
        # 409 — a user with this (unique) username already exists.
        CONTEXT.logger.warning(f"User create rejected (409 duplicate username): username={body.username!r}")
        raise HTTPException(status_code=409, detail=f"A user named {body.username!r} already exists.")

    CONTEXT.logger.info(f"Created user id={response.id} username={body.username!r} role={body.role!r}")
    return response


@router.get("", response_model=UserListResponse)
@auto_handle_errors
async def list_users(_root: Principal = Depends(require_root)) -> UserListResponse:
    """List all application users (root only), newest first."""
    # 1. Read all users
    async with CONTEXT.postgres.session() as session:
        users = await CONTEXT.user_repo.list_users(session)

    # 2. Project to safe response models (no password hash)
    items = [UserResponse.model_validate(u) for u in users]
    return UserListResponse(users=items, total=len(items))


@router.delete("/{user_id}", response_model=DeactivateUserResponse)
@auto_handle_errors
async def deactivate_user(
    user_id: uuid.UUID, root: Principal = Depends(require_root)
) -> DeactivateUserResponse:
    """
    Deactivate a user (root only) — a soft delete that blocks future authentication.

    Soft deactivation (not a hard delete) preserves the user's keys + grants for audit. Root may
    not deactivate itself, which would risk locking everyone out of the instance.
    """
    # 1. Guard against self-lockout — root cannot deactivate its own account
    if user_id == root.user_id:
        # 409 — refusing to deactivate the calling root account (self-lockout protection).
        CONTEXT.logger.warning(f"User deactivate rejected (409 self): user_id={user_id}")
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")

    # 2. Apply the soft toggle; an unknown id yields None → 404
    async with CONTEXT.postgres.session() as session:
        user = await CONTEXT.user_repo.set_active(session, user_id, is_active=False)
    if user is None:
        # 404 — no user with this id.
        CONTEXT.logger.warning(f"User deactivate rejected (404 unknown user): user_id={user_id}")
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    CONTEXT.logger.info(f"Deactivated user id={user_id}")
    return DeactivateUserResponse(deactivated=True, id=user_id)


@router.put("/{user_id}/password", response_model=UserResponse)
@auto_handle_errors
async def reset_password(
    user_id: uuid.UUID,
    body: UpdatePasswordRequest,
    _root: Principal = Depends(require_root),
) -> UserResponse:
    """Reset a user's password (root only). The new password is argon2-hashed before storage."""
    # 1. Hash the new password (plaintext never persisted/logged)
    password_hash = PasswordHelpers.hash(body.password)

    # 2. Apply the new hash; an unknown id yields None → 404
    async with CONTEXT.postgres.session() as session:
        user = await CONTEXT.user_repo.update_password(session, user_id, password_hash)
        response = UserResponse.model_validate(user) if user is not None else None
    if response is None:
        # 404 — cannot reset the password of a user that does not exist.
        CONTEXT.logger.warning(f"Password reset rejected (404 unknown user): user_id={user_id}")
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    CONTEXT.logger.info(f"Password reset for user id={user_id}")
    return response
