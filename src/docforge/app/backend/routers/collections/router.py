# ====== Code Summary ======
# The collections router — the contract's CRUD: create (schema declared up front + pipeline
# blob seeded with the product default), read, patch the config blobs (pipeline VALIDATED
# before storage — a broken graph never reaches the worker), delete, plus the schema-driven
# discovery of the identity/limits contract. Every rejection carries an explicit HTTP code and a
# precise message. Non-route logic lives in helpers.py (pure) and store_sync.py (store follow-through).

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.blob_secrets import restore_blob_secrets
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer
from shared_libs.pipelines.ingest.estimate import CostEstimate
from shared_libs.services.db.facades import CollectionUpdateSpec, DuplicateCollectionNameError
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.corpus import DocumentFilter, DocumentSelector, DocumentSelectorResolver
from ...libs.estimate import CollectionEstimateRequest, EstimateInputError
from ...libs.health import CollectionHealthResponse
from ...libs.logsafe import LogSafeHelpers
from ...libs.reingest import BulkReingestAccepted, BulkReingestRequest, BulkReingestService
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from .blob_helpers import CollectionBlobHelpers
from .helpers import CollectionHelpers
from .models import (
    CollectionContractModel,
    CollectionContractSchemaResponse,
    CollectionListItem,
    CollectionModel,
    CollectionStorageResponse,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from .store_sync import CollectionStoreSync

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get(
    "",
    response_model=list[CollectionListItem],
)
@auto_handle_errors
async def list_collections(
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> list[CollectionListItem]:
    """
    Return every collection the caller may see, with its full schema AND a server-computed health
    summary.

    The health summary is rolled up through the SAME path the detail probe (`GET /{id}/health`) uses,
    so a fleet card's verdict + doc/vector counts + last-ingest can never disagree with the
    collection's own overview — and the front no longer fans out N live probes per page load.

    Returns:
        list[CollectionListItem]: The contracts the key is scoped to (schema included), each with its
        health summary. A scoped key sees only its own collections — never the whole fleet.
    """
    # 1. Rows + their schemas (collection counts stay small — the N+1 is fine here).
    collections = await CONTEXT.database.collections.list_all()

    # 1b. Scope filter — a fleet-wide read must not leak other tenants' contracts (base_urls, models,
    #     schema fields, estimate rates). None = full access (root / auth-off / wildcard key).
    allowed = AuthzGuard.scoped_collections(principal)
    if allowed is not None:
        collections = [c for c in collections if str(c.id) in allowed]

    # 2. Fresh, cheap counters for the WHOLE fleet — three BATCHED grouped queries, no N+1, no Qdrant.
    ids = [c.id for c in collections]
    doc_counts = await CONTEXT.database.documents.count_by_collections(ids)
    chunk_counts = await CONTEXT.database.documents.count_chunks_by_collections(ids)
    last_ingests = await CONTEXT.database.jobs.last_successful_ingest_at_by_collections(ids)

    # 3. Pure, structural-only health roll-up (no provider sweep) — the list's single source of truth,
    #    consistent with the detail overview's structural determination.
    summaries = CONTEXT.health_service.summarize_structural(
        collections,
        doc_counts=doc_counts,
        chunk_counts=chunk_counts,
        last_ingests=last_ingests,
    )

    # 4. Attach each collection's summary to its full contract (masking applied by to_model).
    return [
        CollectionListItem(
            **CollectionHelpers.to_model(
                c, await CONTEXT.database.collections.get_schema(c.id)
            ).model_dump(),
            health=summaries[c.id],
        )
        for c in collections
    ]


@router.get(
    "/contract-schema",
    response_model=CollectionContractSchemaResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_contract_schema() -> CollectionContractSchemaResponse:
    """
    Discover the collection identity/limits contract as JSON Schema — the schema-driven UI form.

    Mirrors a node's ``config_schema`` face so a new scalar contract field auto-surfaces in the UI
    with zero frontend change (the frontend feeds it straight to its existing ``SchemaForm``).

    Returns:
        CollectionContractSchemaResponse: The ``model_json_schema()`` of the identity/limits contract.
    """
    # 1. The schema is derived from the SAME model CreateCollectionRequest composes — no drift.
    return CollectionContractSchemaResponse(
        config_schema=CollectionContractModel.model_json_schema()
    )


@router.get(
    "/{collection_id}",
    response_model=CollectionModel,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_collection(collection_id: uuid.UUID) -> CollectionModel:
    """
    Return one collection's full contract.

    Returns:
        CollectionModel: Identity, limits, schema and config blobs.
    """
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return CollectionHelpers.to_model(
        collection, await CONTEXT.database.collections.get_schema(collection_id)
    )


@router.get(
    "/{collection_id}/health",
    response_model=CollectionHealthResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_collection_health(collection_id: uuid.UUID) -> CollectionHealthResponse:
    """
    Probe a collection's operational health on demand — provider reachability across the ingest AND
    search graphs, index population and last successful ingest — WITHOUT enqueuing a job or spending.

    Returns:
        CollectionHealthResponse: Per-provider reachability, index stats and a rolled-up verdict.
    """
    # 1. Compose the snapshot from the shared build + reachability + index reads (no writes).
    result = await CONTEXT.health_service.check(collection_id)

    # 2. Unknown collection → 404, mirroring the other collection reads.
    if result is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return result


@router.get(
    "/{collection_id}/storage",
    response_model=CollectionStorageResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_collection_storage(collection_id: uuid.UUID) -> CollectionStorageResponse:
    """
    Measure a collection's material footprint per store — how much hardware it occupies.

    S3 bytes are EXACT (content-addressed blob registry, deduped); Postgres and Qdrant bytes are
    ESTIMATES (real row bytes via ``pg_column_size`` / point-count arithmetic). Aggregated in SQL +
    Qdrant count/facet calls — no per-document N+1, no caching. The per-document list is sorted
    heaviest-first, so it doubles as the top-N.

    Returns:
        CollectionStorageResponse: Per-store totals + the per-document breakdown (404 when unknown).
    """
    # 1. Existence first — an unknown collection is a 404, mirroring the other collection reads.
    if await CONTEXT.database.collections.get(collection_id) is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Compose the footprint (grouped aggregates + one Qdrant profile) and shape the response.
    footprint = await CONTEXT.database.storage.collection_footprint(collection_id)
    return CollectionStorageResponse.from_payload(footprint)


@router.post(
    "/{collection_id}/estimate",
    response_model=CostEstimate,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def estimate_collection(
    collection_id: uuid.UUID,
    request: CollectionEstimateRequest | None = None,
) -> CostEstimate:
    """
    Preview the projected cost (tokens + $) and volume of ingesting a collection's documents.

    A PRE-hoc ESTIMATE — no job is enqueued, nothing is spent. It reads the collection's ACTUAL
    pipeline config (only enabled cost-incurring stages are costed) and cheap per-document stats,
    then projects per-stage usage and cost against the same rate model as the post-hoc meter. The
    assumptions it rests on are echoed in the response; a stage whose model has no known rate is
    reported with a null cost (tokens still shown), never a fabricated number.

    The covered documents default to the pending scope, but the body may target an explicit
    ``document_ids`` subset or a corpus ``filter`` (the SAME filter shape the document grid uses).

    Returns:
        CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats
        (404 when the collection is unknown; 422 when its stored pipeline blob is unreadable, or a
        bad document id / corpus filter was supplied).
    """
    # 1. Default the body — the endpoint is callable with no payload (scope defaults to pending).
    payload = request or CollectionEstimateRequest()

    # 2. Run the estimate; an unreadable blob or a bad id/filter is a 422 (mirrors reingest), unknown
    #    a 404. The catch is NARROW on purpose: EstimateInputError is only the caller-input faults
    #    (non-UUID id, unknown/foreign id, bad filter). An unrelated ValueError from the estimator's
    #    arithmetic is deliberately NOT swallowed here — it surfaces as a 500 (a real bug), never a 422.
    try:
        estimate = await CONTEXT.estimate_service.estimate(collection_id, payload)
    except BlobNormalizationError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    except EstimateInputError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    if estimate is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return estimate


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
    blob = CollectionBlobHelpers.canonical_pipeline(
        request.pipeline or CollectionBlobHelpers.preset_blob(request.preset)
    )

    # 2. Name unicity — explicit 409, not a driver error.
    if await CONTEXT.database.collections.get_by_name(request.name) is not None:
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")

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
                pipeline=blob,
                search={},
            ),
            rows,
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
    return CollectionHelpers.to_model(
        created, await CONTEXT.database.collections.get_schema(created.id)
    )


@router.patch(
    "/{collection_id}",
    response_model=CollectionModel,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def update_collection(
    collection_id: uuid.UUID, request: UpdateCollectionRequest
) -> CollectionModel:
    """
    Patch identity/limits, the metadata schema (by DIFF), and/or the config blobs.

    Returns:
        CollectionModel: The updated contract; 404 unknown, 409 name clash, 422 broken
        pipeline or colliding vector slugs.
    """
    # 1. Existence first — every later step assumes the row.
    current = await CONTEXT.database.collections.get(collection_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Renaming keeps names unique — explicit 409, not a driver error.
    if request.name is not None and request.name != current.name:
        if await CONTEXT.database.collections.get_by_name(request.name) is not None:
            raise HTTPException(
                status_code=409, detail=f"Collection '{request.name}' already exists."
            )

    # 3. Restore any masked provider secret BEFORE validating/storing: a caller that read a collection
    #    (secrets masked) and PATCHed a blob back sends the mask verbatim — that means "keep the stored
    #    key", never "set the key to the literal mask". Healed against the real stored blobs by node id.
    healed_pipeline = (
        restore_blob_secrets(request.pipeline, current.pipeline)
        if request.pipeline is not None
        else None
    )
    healed_search = (
        restore_blob_secrets(request.search, current.search) if request.search is not None else None
    )

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

    # 3c. Validate the schema diff BEFORE any write — a bad field must 422 without touching the store.
    if request.fields is not None:
        CollectionHelpers.validate_fields(request.fields)

    # 4. An embed-space change (different embedder model/provider, toggled sparse) forces a reindex —
    #    a PURE comparison of the current vs stored blob, computed before the write. None leaves the
    #    flag as-is (a schema change may already have set it inside the same transaction). Otherwise
    #    new documents would embed into a space incompatible with the stored ones, degrading search.
    reindex_from_embed: bool | None = None
    if stored_pipeline is not None and CollectionBlobHelpers.embed_space_changed(
        current.pipeline, stored_pipeline
    ):
        reindex_from_embed = True
        CONTEXT.logger.warning(
            f"Collection {collection_id}: embed vector space changed — reindex required"
        )

    # 5. Apply EVERY DB part in ONE transaction — a mid-sequence failure rolls the WHOLE patch back,
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
            )
        ),
        name=request.name,
        supported_formats=request.supported_formats,
        tags=request.tags,
        max_file_size_bytes=request.max_file_size_bytes,
        job_timeout_seconds=request.job_timeout_seconds,
        schema_fields=CollectionHelpers.to_field_rows(request.fields)
        if request.fields is not None
        else None,
        config_touched=request.pipeline is not None or request.search is not None,
        pipeline=stored_pipeline,
        search=healed_search,
        embed_reindex=reindex_from_embed,
        note=request.note,
        apply_overrides="estimate_overrides" in request.model_fields_set,
        estimate_overrides=request.estimate_overrides.model_dump(mode="json", exclude_none=True)
        if request.estimate_overrides is not None
        else None,
    )
    try:
        result = await CONTEXT.database.collections.apply_update(collection_id, spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except DuplicateCollectionNameError:
        # A rename lost the UNIQUE race after the pre-check — same 409 the pre-check returns.
        raise HTTPException(status_code=409, detail=f"Collection '{request.name}' already exists.")

    # 6. Store-side follow-through AFTER the DB commit — reconcile the Qdrant store to the new schema
    #    (a newly-filterable field gets its payload index added live; the backfills repopulate existing
    #    points) then enqueue the repair backfills. Kept OUT of the DB transaction on purpose: it is
    #    non-transactional and best-effort. A newly semantic/lexical field needs a named vector Qdrant
    #    cannot add live, so a reindex is required to make it searchable.
    if result.schema_applied:
        await CollectionStoreSync.reconcile_and_backfill(collection_id)
        if result.schema_reindex_required:
            CONTEXT.logger.warning(
                f"Collection {collection_id}: searchable schema changed — reindex required"
            )

    updated = await CONTEXT.database.collections.get(collection_id)
    return CollectionHelpers.to_model(
        updated, await CONTEXT.database.collections.get_schema(collection_id)
    )


@router.post(
    "/{collection_id}/reingest",
    response_model=BulkReingestAccepted,
    status_code=202,
)
@auto_handle_errors
async def reingest_collection(
    collection_id: uuid.UUID,
    request: BulkReingestRequest,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> BulkReingestAccepted:
    """
    Re-run the full pipeline over a collection's corpus — all documents, or an explicit subset.

    The run is idempotent per document (a REPLACE at every layer: chunks/IR purged-then-inserted,
    Qdrant points deleted-by-document before upsert) and the original bytes are already stored, so
    this never re-uploads. Each document gets a FRESH job; poll each returned job for progress.

    Returns:
        BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run (202);
            404 when the collection is unknown, 422 on a stale/broken pipeline or a bad document subset.
    """
    # 1. The collection must exist — its budget + pipeline drive every run.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Belt-and-suspenders: require(WRITE) already collection-scopes the `collection_id` path
    #    param before this body runs, so a cross-tenant key is a 403 there; this restates it locally.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 3. Fail-fast on a STALE/broken pipeline BEFORE minting any job — auto-heal then structurally
    #    validate the blob, exactly as an upload does, so a broken collection surfaces once here
    #    instead of as N failed jobs.
    try:
        pipeline_blob = BlobNormalizer.normalize(collection.pipeline)
    except BlobNormalizationError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    PipelineBlobValidator.validate(pipeline_blob)

    # 4. Map the request to the SHARED DocumentSelector: an explicit subset → id mode (validated to
    #    exist AND belong here by the resolver), or omitted → filter mode with an EMPTY filter (the
    #    whole collection). This reuses the corpus route's resolution + ownership guards instead of a
    #    hand-duplicated id-validation block. An empty explicit list is an ambiguous no-op — rejected.
    if request.document_ids is not None:
        if not request.document_ids:
            raise HTTPException(
                status_code=422, detail="document_ids must be a non-empty list or omitted."
            )
        try:
            selector = DocumentSelector(
                document_ids=[uuid.UUID(value) for value in request.document_ids]
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"document_ids: not a UUID ({exc}).")
    else:
        selector = DocumentSelector(filter=DocumentFilter())

    schema = await CONTEXT.database.collections.get_schema(collection_id)
    try:
        matched = await DocumentSelectorResolver(CONTEXT.database).resolve(
            collection_id, selector, schema
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 5. Fan out through the SHARED capped path — a huge corpus enqueues only the first N and reports
    #    capped=true (never silently floods the queue), exactly like the corpus selector route.
    service = BulkReingestService(CONTEXT.database, CONTEXT.queue)
    result = await service.enqueue_capped(
        collection, matched, RUNTIME_CONFIG.CORPUS_MAX_REINGEST_FANOUT, force=request.force
    )
    return BulkReingestAccepted(
        collection_id=str(collection_id),
        count=result.enqueued,
        matched=result.matched,
        enqueued=result.enqueued,
        capped=result.capped,
        max_fanout=result.ceiling,
        jobs=result.handles,
    )


@router.delete(
    "/{collection_id}",
    status_code=204,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def delete_collection(collection_id: uuid.UUID) -> None:
    """
    Delete a collection (404 when unknown).
    """
    deleted = await CONTEXT.database.collections.delete(collection_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    CONTEXT.logger.info(f"Collection {collection_id} deleted")


__all__ = ["router"]
