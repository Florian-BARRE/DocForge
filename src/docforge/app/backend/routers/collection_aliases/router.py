# ====== Code Summary ======
# The collection-alias router — GET /collection-aliases (the aliases whose target the caller may see),
# PUT /collection-aliases/{name} (create, or atomically re-point = the "switch") and DELETE. Writes need
# a FULL-ACCESS (unscoped) admin key: re-pointing or re-creating an alias re-scopes every key bound to
# `alias:<name>` — including keys a scoped admin could never manage — so it is root-grade. A delete is
# refused while live keys still name the alias (a freed name would re-bind them to whoever re-creates
# it). Every write is recorded by the audit middleware (target type `collection_alias`, id = the name).

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Response

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    CollectionAliasConflictError,
    CollectionAliasInUseError,
    CollectionAliasNameClashError,
    CollectionAliasTargetMissingError,
)

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionAliasName
from ...utils.error_handling import auto_handle_errors
from .models import CollectionAliasModel, SetCollectionAliasRequest, SetCollectionAliasResponse

router = APIRouter(prefix="/collection-aliases", tags=["collection-aliases"])


def _assert_full_access(principal: AuthPrincipal) -> None:
    """Refuse an alias write from a collection-scoped key (403) — alias writes are root-grade."""
    if not principal.is_full_access:
        raise HTTPException(
            status_code=403,
            detail="Collection alias writes require a full-access (unscoped) admin key: an alias "
            "re-scopes every API key bound to it.",
        )


@router.get("", response_model=list[CollectionAliasModel])
@auto_handle_errors
async def list_collection_aliases(
    principal: AuthPrincipal = Depends(require(Capability.READ_TEXT)),
) -> list[CollectionAliasModel]:
    """
    List the collection aliases whose target collection the caller may see, by name.

    Returns:
        list[CollectionAliasModel]: Each alias with its current target (id + name).
    """
    # 1. Every alias + the collection names, then keep the ones targeting an in-scope collection.
    aliases = await CONTEXT.database.collection_aliases.list_all()
    names = {c.id: c.name for c in await CONTEXT.database.collections.list_all()}
    allowed = AuthzGuard.scoped_collections(principal)
    return [
        CollectionAliasModel(
            name=alias.name,
            collection_id=str(alias.collection_id),
            collection_name=names.get(alias.collection_id, ""),
            created_at=alias.created_at,
            updated_at=alias.updated_at,
        )
        for alias in aliases
        if allowed is None or str(alias.collection_id) in allowed
    ]


@router.put("/{name}", response_model=SetCollectionAliasResponse)
@auto_handle_errors
async def set_collection_alias(
    name: str,
    payload: SetCollectionAliasRequest,
    response: Response,
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> SetCollectionAliasResponse:
    """
    Create the alias, or atomically re-point it to another collection (the "switch").

    Returns:
        SetCollectionAliasResponse: The alias now (201 created, 200 re-pointed) + its previous
        target; 422 bad name, 404 unknown collection, 409 name clash with a collection, 403 scope.
    """
    # 1. Name grammar (slug, not UUID-shaped, not a reserved /collections segment).
    problem = CollectionAliasName.problem(name)
    if problem is not None:
        raise HTTPException(status_code=422, detail=problem)

    # 2. Alias writes are full-access only: an alias re-scopes EVERY key that names it, including
    #    keys the caller could never manage, so no scoped admin may move or claim one.
    _assert_full_access(principal)
    AuthzGuard.assert_collection_scope(principal, str(payload.collection_id))

    def _authorize_previous(previous: object) -> None:
        if previous is not None:
            AuthzGuard.assert_collection_scope(principal, str(previous))

    # 3. The atomic create / re-point; domain refusals map to explicit codes.
    try:
        write = await CONTEXT.database.collection_aliases.set(
            name, payload.collection_id, _authorize_previous
        )
    except CollectionAliasTargetMissingError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (CollectionAliasNameClashError, CollectionAliasConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # 4. Answer with the new state (201 on creation).
    collection = await CONTEXT.database.collections.get(write.collection_id)
    if write.previous_collection_id is None:
        response.status_code = 201
    CONTEXT.logger.info(
        f"Collection alias '{name}' → {write.collection_id} (was {write.previous_collection_id})"
    )
    return SetCollectionAliasResponse(
        name=write.name,
        collection_id=str(write.collection_id),
        collection_name=collection.name if collection is not None else "",
        created_at=write.created_at,
        updated_at=write.updated_at,
        previous_collection_id=(
            str(write.previous_collection_id) if write.previous_collection_id else None
        ),
        created=write.previous_collection_id is None,
    )


@router.delete("/{name}", status_code=204)
@auto_handle_errors
async def delete_collection_alias(
    name: str,
    principal: AuthPrincipal = Depends(require(Capability.ADMIN)),
) -> None:
    """
    Delete a collection alias (keys scoped to ``alias:<name>`` then grant nothing through it).

    Returns:
        None: 204; 404 unknown alias, 403 when a scoped admin does not own its target.
    """

    # 1. Full access only (see set_collection_alias); refused while live keys still name it.
    _assert_full_access(principal)

    def _authorize_target(target: object) -> None:
        if target is not None:
            AuthzGuard.assert_collection_scope(principal, str(target))

    try:
        deleted = await CONTEXT.database.collection_aliases.delete(name, _authorize_target)
    except CollectionAliasInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection alias '{name}' not found.")
    CONTEXT.logger.info(f"Collection alias '{name}' deleted")


__all__ = ["router"]
