# ====== Code Summary ======
# Per-collection collaborators sub-resource: list grants / set a user's role / revoke a grant.
# Every route requires the ADMIN role on the target collection (root is implicitly admin). Mounted
# under /api/v1/collections/{collection_id}/access. The router-level dependency enforces admin once
# for all routes so each handler can focus on the grant mutation itself.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Principal, require_collection_role
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.access.models import (
    AccessGrantResponse,
    AccessListResponse,
    RevokeAccessResponse,
    SetAccessRequest,
)
from common_libs.storage.postgres.models import GrantRole

# Managing collaborators is an admin-level action — enforced once at the router level so every
# route below inherits the admin gate (root passes implicitly).
router = APIRouter(
    tags=["access"],
    dependencies=[Depends(require_collection_role(GrantRole.ADMIN))],
)


async def _require_collection(collection_id: uuid.UUID) -> None:
    """
    Ensure the target collection exists, else 404.

    Authorization (admin) has already passed at the router level, so revealing existence here is
    safe — only an admin/root reaches this point.

    Args:
        collection_id (uuid.UUID): The collection to check.

    Raises:
        HTTPException: 404 when the collection does not exist.
    """
    # 1. Existence check
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — access management requested for a collection that does not exist.
        CONTEXT.logger.warning(
            f"Access request rejected (404 unknown collection): collection={collection_id}"
        )
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")


@router.get("", response_model=AccessListResponse)
@auto_handle_errors
async def list_access(collection_id: uuid.UUID) -> AccessListResponse:
    """List a collection's collaborators and their roles (admin only)."""
    # 1. Collection must exist
    await _require_collection(collection_id)

    # 2. Read grants + resolve usernames for display
    async with CONTEXT.postgres.session() as session:
        grants = await CONTEXT.grant_repo.list_for_collection(session, collection_id)
        items: list[AccessGrantResponse] = []
        for g in grants:
            owner = await CONTEXT.user_repo.get_by_id(session, g.user_id)
            items.append(
                AccessGrantResponse(
                    user_id=g.user_id,
                    username=owner.username if owner is not None else None,
                    role=g.role,
                    granted_by=g.granted_by,
                    created_at=g.created_at,
                )
            )
    return AccessListResponse(collection_id=collection_id, grants=items, total=len(items))


@router.put("/{user_id}", response_model=AccessGrantResponse)
@auto_handle_errors
async def set_access(
    collection_id: uuid.UUID,
    user_id: uuid.UUID,
    body: SetAccessRequest,
    actor: Principal = Depends(require_collection_role(GrantRole.ADMIN)),
) -> AccessGrantResponse:
    """
    Grant or update a user's role on the collection (admin only).

    Idempotent on (user, collection): re-setting a role updates the existing grant. The grantee
    must be a known user.
    """
    # 1. Collection must exist
    await _require_collection(collection_id)

    # 2. Grantee must be a known user (cannot grant access to a phantom id)
    async with CONTEXT.postgres.session() as session:
        target = await CONTEXT.user_repo.get_by_id(session, user_id)
    if target is None:
        # 404 — cannot grant a collection role to a user that does not exist.
        CONTEXT.logger.warning(
            f"Set access rejected (404 unknown user): collection={collection_id} user={user_id}"
        )
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    # 3. Upsert the grant, recording the actor as granter (audit)
    async with CONTEXT.postgres.session() as session:
        grant = await CONTEXT.grant_repo.upsert(
            session,
            user_id=user_id,
            collection_id=collection_id,
            role=GrantRole(body.role).value,
            granted_by=actor.user_id,
        )
        username = target.username

    CONTEXT.logger.info(
        f"Set access collection={collection_id} user={user_id} role={body.role!r} "
        f"by={actor.user_id}"
    )
    return AccessGrantResponse(
        user_id=grant.user_id,
        username=username,
        role=grant.role,
        granted_by=grant.granted_by,
        created_at=grant.created_at,
    )


@router.delete("/{user_id}", response_model=RevokeAccessResponse)
@auto_handle_errors
async def revoke_access(
    collection_id: uuid.UUID, user_id: uuid.UUID
) -> RevokeAccessResponse:
    """Revoke a user's grant on the collection (admin only)."""
    # 1. Collection must exist
    await _require_collection(collection_id)

    # 2. Delete the grant; absence yields 404 (nothing to revoke)
    async with CONTEXT.postgres.session() as session:
        deleted = await CONTEXT.grant_repo.delete(session, user_id, collection_id)
    if not deleted:
        # 404 — the user holds no grant on this collection, so there is nothing to revoke.
        CONTEXT.logger.warning(
            f"Revoke access rejected (404 no grant): collection={collection_id} user={user_id}"
        )
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} has no grant on collection {collection_id}.",
        )

    CONTEXT.logger.info(f"Revoked access collection={collection_id} user={user_id}")
    return RevokeAccessResponse(revoked=True, collection_id=collection_id, user_id=user_id)
