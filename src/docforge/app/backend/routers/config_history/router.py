# ====== Code Summary ======
# The versioned config history of a collection — GET /collections/{id}/config-versions (paginated,
# newest first, with author + change summary), GET …/diff?from=&to= (structured masked diff), GET
# …/{version} (one masked snapshot) and POST …/{version}/restore (re-apply as a NEW version through the
# PATCH write path). Reads need READ_TECHNICAL, restore needs WRITE (its response carries no blob);
# all are collection-scoped by the path param.
# Orchestration lives in ConfigHistoryService. The diff route is declared before /{version} so the
# literal segment is never parsed as a version number.

# ====== Standard Library Imports ======

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import SecretReentryRequired

# ====== Local Project Imports ======
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.config_history import ConfigAuthorResolver
from ...utils.error_handling import auto_handle_errors
from .models import (
    ConfigVersionDetail,
    ConfigVersionDiffResponse,
    ConfigVersionListResponse,
    ConfigVersionRestoreResponse,
)
from .service import ConfigHistoryService

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get(
    "/{collection_id}/config-versions",
    response_model=ConfigVersionListResponse,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def list_config_versions(
    collection_id: CollectionRef,
    limit: int = Query(default=50, ge=1, le=200, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Newer versions to skip (paging)."),
) -> ConfigVersionListResponse:
    """
    List a collection's config versions, newest first, with who wrote each and what it changed.

    Returns:
        ConfigVersionListResponse: The page + total; 404 unknown collection.
    """
    # 1. Page the history; each item is summarised against the version just before it.
    return await ConfigHistoryService.list_page(collection_id, limit, offset)


@router.get(
    "/{collection_id}/config-versions/diff",
    response_model=ConfigVersionDiffResponse,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def diff_config_versions(
    collection_id: CollectionRef,
    from_version: int = Query(..., alias="from", ge=1, description="The base version."),
    to_version: int = Query(..., alias="to", ge=1, description="The compared version."),
) -> ConfigVersionDiffResponse:
    """
    Diff two config versions path by path (graph nodes keyed by id); secrets are always masked, so
    a rotated key shows as a change with both sides masked.

    Returns:
        ConfigVersionDiffResponse: The added / removed / changed paths; 404 unknown collection/version.
    """
    # 1. Both snapshots are read, diffed on their real values, reported masked.
    return await ConfigHistoryService.diff(collection_id, from_version, to_version)


@router.get(
    "/{collection_id}/config-versions/{version}",
    response_model=ConfigVersionDetail,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def get_config_version(collection_id: CollectionRef, version: int) -> ConfigVersionDetail:
    """
    Read one config version — its {pipeline, search} snapshot with every provider secret masked.

    Returns:
        ConfigVersionDetail: The version metadata + masked snapshot; 404 unknown collection/version.
    """
    # 1. Serve the stored snapshot through the export's redaction (never a live key).
    return await ConfigHistoryService.get(collection_id, version)


@router.post(
    "/{collection_id}/config-versions/{version}/restore",
    response_model=ConfigVersionRestoreResponse,
)
@auto_handle_errors
async def restore_config_version(
    collection_id: CollectionRef,
    version: int,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> ConfigVersionRestoreResponse:
    """
    Restore a config version: its {pipeline, search} is re-applied through the PATCH write path as a
    NEW version noted "restore of v{N}" (history is never rewritten; the metadata schema is not
    versioned and is left as is).

    Secrets: the stored snapshot holds real keys, but a provider that still exists at the SAME
    endpoint keeps its CURRENT key (a key rotated since is never rolled back); a provider whose current
    key lives at a DIFFERENT endpoint is refused with a 422 (re-enter it with a PATCH); a provider with
    no current key gets the snapshot's own key back (same endpoint it was stored with).

    Returns:
        ConfigVersionRestoreResponse: The new version + derived reindex flag; 404 unknown
        collection/version, 422 secret re-entry or an invalid/unmigratable snapshot, 409 concurrent write.
    """
    # 1. Belt-and-suspenders scope check (require(WRITE) already scoped the path param).
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Resolve secrets → validate → CAS write a new version stamped with the caller as author.
    author = ConfigAuthorResolver.from_principal(principal)
    try:
        return await ConfigHistoryService.restore(collection_id, version, author)
    except SecretReentryRequired as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Collection {collection_id}: cannot restore v{version}: {exc} (re-enter it with "
            f"PATCH /collections/{collection_id}).",
        )


__all__ = ["router"]
