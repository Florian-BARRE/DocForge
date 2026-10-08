# ====== Code Summary ======
# Collection PATCH route — patch identity/limits, the metadata schema and/or the config blobs in ONE
# transaction (secrets restored, pipeline healed + validated, schema change resolved BEFORE any write;
# ``dry_run`` returns the schema diff only), then the store-side follow-through after the commit.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import SecretReentryRequired, restore_blob_secrets
from shared_libs.services.db.facades import CollectionUpdateSpec, DuplicateCollectionNameError

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.config_history import ConfigAuthorResolver
from ...utils.error_handling import auto_handle_errors
from .blob_helpers import CollectionBlobHelpers
from .helpers import CollectionHelpers
from .models import UpdateCollectionRequest, UpdateCollectionResponse
from .name_guard import CollectionNameGuard
from .schema_patch import CollectionSchemaPatch
from .store_sync import CollectionStoreSync
from .technical_view import CollectionTechnicalView

router = APIRouter(prefix="/collections", tags=["collections"])


@router.patch(
    "/{collection_id}",
    response_model=UpdateCollectionResponse,
)
@auto_handle_errors
async def update_collection(
    collection_id: CollectionRef,
    request: UpdateCollectionRequest,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> UpdateCollectionResponse:
    """
    Patch identity/limits, the metadata schema (legacy ``fields`` list or explicit ``field_ops``),
    and/or the config blobs. ``dry_run`` validates everything and returns the schema diff only.

    Returns:
        UpdateCollectionResponse: The updated contract (unchanged under dry_run) + its schema_diff;
        404 unknown, 409 name clash, 422 broken pipeline, bad field op or colliding vector slugs.
    """
    # 1. Existence first — every later step assumes the row.
    current = await CONTEXT.database.collections.get(collection_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Renaming keeps names unique (collections + collection aliases) — explicit 409.
    if request.name is not None and request.name != current.name:
        await CollectionNameGuard.assert_free(request.name)

    # 3. Restore any masked provider secret BEFORE validating/storing: a caller that read a collection
    #    (secrets masked) and PATCHed a blob back sends the mask verbatim — that means "keep the stored
    #    key", never "set the key to the literal mask". Healed against the real stored blobs by node id.
    #    A masked/omitted secret whose provider endpoint changed is refused (422): it must be
    #    re-entered, never carried to the new host nor silently blanked.
    try:
        healed_pipeline = (
            restore_blob_secrets(request.pipeline, current.pipeline)
            if request.pipeline is not None
            else None
        )
        healed_search = (
            restore_blob_secrets(request.search, current.search)
            if request.search is not None
            else None
        )
    except SecretReentryRequired as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")

    # 3a. A new pipeline never reaches storage broken: heal it to the current engine, validate it,
    #     and keep its stamped canonical form for storage (step 6).
    stored_pipeline = (
        CollectionBlobHelpers.canonical_pipeline(healed_pipeline)
        if healed_pipeline is not None
        else None
    )

    # 3b. A new search blob is a search GRAPH blob: {} (stock default) is always allowed; a non-empty
    #     one is shape-guarded and validated as a genuine SEARCH pipeline before it can be stored.
    if healed_search is not None and healed_search != {}:
        CollectionHelpers.validate_search_blob(healed_search)

    # 3c. Resolve + validate the schema change (fields OR field_ops) and its diff BEFORE any write —
    #     a bad op/field 422s without touching the store; dry_run and apply share this exact path.
    schema = await CollectionSchemaPatch.resolve(current, request)

    # 3d. An explicit title_field must name a document-scope field of the POST-PATCH schema (the new
    #     fields when this PATCH also edits them, else the stored schema); null clears it.
    apply_title_field = "title_field" in request.model_fields_set
    if apply_title_field:
        effective_schema = (
            schema.plan.target
            if schema is not None
            else await CONTEXT.database.collections.get_schema(collection_id)
        )
        CollectionHelpers.validate_title_field(request.title_field, effective_schema)

    # 3e. dry_run stops here: everything validated, the diff computed, nothing written.
    if request.dry_run:
        preview = CollectionHelpers.to_update_response(
            current,
            await CONTEXT.database.collections.get_schema(collection_id),
            schema,
            True,
            await CollectionStoreSync.index_gaps(collection_id, schema, dry_run=True),
        )
        return CollectionTechnicalView.shape([preview], principal)[0]

    # 4. Apply EVERY DB part in ONE transaction — a mid-sequence failure rolls the WHOLE patch back,
    #    so a collection is never left half-updated (e.g. contract changed but schema not). The
    #    pipeline is stored in its stamped canonical form (subsequent runs/uploads fast-path). A
    #    vector-slug collision surfaces as ValueError → 422, before any write touches the DB.
    spec = CollectionUpdateSpec(
        contract_touched=any(
            v is not None
            for v in (
                request.name,
                request.supported_formats,
                request.tags,
                request.max_file_size_bytes,
                request.job_timeout_seconds,
                request.trace_verbosity,
            )
        ),
        name=request.name,
        supported_formats=request.supported_formats,
        tags=request.tags,
        max_file_size_bytes=request.max_file_size_bytes,
        job_timeout_seconds=request.job_timeout_seconds,
        trace_verbosity=request.trace_verbosity,
        schema_fields=schema.rows if schema is not None else None,
        schema_renames=dict(schema.plan.renames) if schema is not None else {},
        config_touched=request.pipeline is not None or request.search is not None,
        pipeline=stored_pipeline,
        search=healed_search,
        note=request.note,
        author=ConfigAuthorResolver.from_principal(principal),
        apply_overrides="estimate_overrides" in request.model_fields_set,
        estimate_overrides=request.estimate_overrides.model_dump(mode="json", exclude_none=True)
        if request.estimate_overrides is not None
        else None,
        apply_title_field=apply_title_field,
        title_field=request.title_field,
    )
    try:
        result = await CONTEXT.database.collections.apply_update(collection_id, spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DuplicateCollectionNameError:
        # A rename lost the UNIQUE race after the pre-check — same 409 the pre-check returns.
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")

    # 5. Store-side follow-through AFTER the DB commit — reconcile the Qdrant store to the new schema
    #    (a newly-filterable field gets its payload index added live; the backfills repopulate existing
    #    points) then enqueue the repair backfills. Kept OUT of the DB transaction on purpose: it is
    #    non-transactional and best-effort. A newly semantic/lexical field needs a named vector Qdrant
    #    cannot add live: it is reported in missing_vectors / reindex_required_fields until rebuilt.
    if result.schema_applied and schema is not None:
        await CollectionStoreSync.reconcile_and_backfill(collection_id, schema.departed)
    if result.schema_reindex_required:
        CONTEXT.logger.warning(
            f"Collection {collection_id}: reindex-relevant config changed — reindex required"
        )

    updated = await CONTEXT.database.collections.get(collection_id)
    response = CollectionHelpers.to_update_response(
        updated,
        await CONTEXT.database.collections.get_schema(collection_id),
        schema,
        False,
        await CollectionStoreSync.index_gaps(collection_id, schema, dry_run=False),
    )
    # A writer without READ_TECHNICAL gets the lean contract back (blobs nulled, never echoed).
    return CollectionTechnicalView.shape([response], principal)[0]


__all__ = ["router"]
