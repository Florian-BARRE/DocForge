# ====== Code Summary ======
# Collection lifecycle routes — create a collection from A to Z (schema declared up front + the
# pipeline/search blobs seeded from their presets, validated BEFORE any store touch) and delete it
# (guarded against an active index rebuild and against aliases still targeting it).

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import (
    CollectionAliasedError,
    DuplicateCollectionNameError,
    IndexRebuildActiveError,
)
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.config_history import ConfigAuthorResolver
from ...libs.index_rebuild import IndexRebuildGuards
from ...libs.logsafe import LogSafeHelpers
from ...utils.error_handling import auto_handle_errors
from .blob_helpers import CollectionBlobHelpers
from .helpers import CollectionHelpers
from .models import CollectionModel, CreateCollectionRequest
from .name_guard import CollectionNameGuard
from .store_sync import CollectionStoreSync
from .technical_view import CollectionTechnicalView

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "",
    response_model=CollectionModel,
    status_code=201,
)
@auto_handle_errors
async def create_collection(
    request: CreateCollectionRequest,
    principal: AuthPrincipal = Depends(require(Capability.CREATE)),
) -> CollectionModel:
    """
    Create a collection from A to Z — contract + full schema + pipeline blob.

    Requires the CREATE capability. A scoped key that creates a collection is auto-granted ownership
    of it: the new id is appended to the key's own ``collections`` scope, so the same key can then
    fully manage what it just created (per its other capabilities) without knowing ids in advance.

    Returns:
        CollectionModel: The created contract (201); 409 on name clash, 422 on bad
        pipeline or colliding vector slugs.
    """
    # 1. Structural validation FIRST — fail-fast BEFORE any store touch (invariant #4), so a malformed
    #    request is a clean 422 even when the DB is unreachable (never a 500 from a driver error).
    #    Fields, then the pipeline blob: the caller's explicit graph wins, otherwise the stock blob the
    #    ``preset`` selects (light = enrichment-free core), healed to the current engine and validated.
    CollectionHelpers.validate_fields(request.fields)
    CollectionHelpers.validate_title_field(request.title_field, request.fields)
    blob = CollectionBlobHelpers.canonical_pipeline(
        request.pipeline or CollectionBlobHelpers.preset_blob(request.preset)
    )

    # 1b. Resolve the SEARCH blob from its preset: the default (or omitted) keeps the {} stock-default
    #     sentinel; a non-default preset is a real search graph, validated exactly as an explicit one.
    search_blob = CollectionBlobHelpers.search_preset_blob(request.search_preset)
    if search_blob:
        CollectionHelpers.validate_search_blob(search_blob)

    # 2. Name unicity (among collections AND collection aliases) — explicit 409, not a driver error.
    await CollectionNameGuard.assert_free(request.name)

    # 3. Create contract + schema in one transaction (slug collisions → explicit 422). A concurrent
    #    create can slip between the step-2 name pre-check and this insert; the façade turns that
    #    UNIQUE-constraint race into DuplicateCollectionNameError → the SAME 409 the pre-check returns
    #    (never a raw 500 from the driver error).
    rows = CollectionHelpers.to_field_rows(request.fields)
    try:
        created = await CONTEXT.database.collections.create(
            Collection(
                name=request.name,
                supported_formats=request.supported_formats,
                tags=request.tags or [],
                max_file_size_bytes=request.max_file_size_bytes,
                job_timeout_seconds=request.job_timeout_seconds,
                trace_verbosity=request.trace_verbosity,
                pipeline=blob,
                search=search_blob,
                title_field=request.title_field,
            ),
            rows,
            author=ConfigAuthorResolver.from_principal(principal),
        )
    except DuplicateCollectionNameError:
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Ownership: a scoped, list-scoped key that just created this collection is granted access to
    #    it by appending the id to its own scope (root / wildcard keys already cover everything).
    await CollectionStoreSync.grant_creator_scope(principal, str(created.id))

    CONTEXT.logger.info(
        f"Collection '{LogSafeHelpers.sanitize(request.name)}' created ({len(rows)} fields)"
    )
    model = CollectionHelpers.to_model(
        created, await CONTEXT.database.collections.get_schema(created.id)
    )
    # A creator without READ_TECHNICAL (e.g. a create+write key) gets the lean contract back.
    return CollectionTechnicalView.shape([model], principal)[0]


@router.delete(
    "/{collection_id}",
    status_code=204,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def delete_collection(collection_id: CollectionRef) -> None:
    """
    Delete a collection (404 when unknown; 409 ``rebuild_index_active`` while an index rebuild runs;
    409 while collection aliases still target it — re-point or delete them first).
    """
    try:
        deleted = await CONTEXT.database.collections.delete(collection_id)
    except IndexRebuildActiveError as exc:
        raise IndexRebuildGuards.active_conflict(exc)
    except CollectionAliasedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    CONTEXT.logger.info(f"Collection {collection_id} deleted")


__all__ = ["router"]
