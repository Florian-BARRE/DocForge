# ====== Code Summary ======
# Collection corpus-maintenance routes — re-run the pipeline over a collection's corpus (whole or an
# explicit subset, optionally replayed from a stage; capped fan-out + estimate/queue guardrails) and
# reclaim the heavy stored execution-trace payloads of its terminal jobs.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.admission import QueueAdmission, ReingestEstimateGate
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.corpus import DocumentFilter, DocumentSelector, DocumentSelectorResolver
from ...libs.estimate import CollectionEstimateRequest
from ...libs.reingest import (
    BulkReingestAccepted,
    BulkReingestRequest,
    BulkReingestService,
    ReplayGuard,
)
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from .models import TracePurgeResult

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "/{collection_id}/reingest",
    response_model=BulkReingestAccepted,
    status_code=202,
)
@auto_handle_errors
async def reingest_collection(
    collection_id: CollectionRef,
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
            404 when the collection is unknown, 422 on a stale/broken pipeline, a bad document subset
            or an unreplayable stage, 409 ``estimate_required`` above the confirm threshold without
            ``confirm_estimate``, 429 ``queue_saturated`` (+ Retry-After) on a saturated queue.
    """
    # 1. The collection must exist — its job timeout + pipeline drive every run.
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
    # 3b. A replay must be honourable by THIS pipeline (422 names why + the allowed stages).
    ReplayGuard.assert_replayable(collection, request.replay_from)

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

    # 4b. A LARGE reingest must be acknowledged (409 estimate_required carries the estimate over the
    #     SAME targets, priced on the replayed stages only when replay_from is set).
    await ReingestEstimateGate(
        CONTEXT.estimate_service, RUNTIME_CONFIG.CORPUS_REINGEST_CONFIRM_THRESHOLD
    ).require(
        collection_id,
        len(matched),
        request.confirm_estimate,
        CollectionEstimateRequest(document_ids=[str(document_id) for document_id in matched]),
        replay_from=request.replay_from,
        technical=AuthzGuard.holds(principal, Capability.READ_TECHNICAL),
    )

    # 5. Fan out through the SHARED capped path — a huge corpus enqueues only the first N and reports
    #    capped=true (never silently floods the queue), exactly like the corpus selector route; the
    #    queue backpressure (429) is applied before any job is minted.
    service = BulkReingestService(CONTEXT.database, CONTEXT.queue)
    result = await service.enqueue_capped(
        collection,
        matched,
        RUNTIME_CONFIG.CORPUS_MAX_REINGEST_FANOUT,
        force=request.force,
        replay_from=request.replay_from,
        admission=QueueAdmission(
            CONTEXT.queue, RUNTIME_CONFIG.QUEUE_MAX_DEPTH, RUNTIME_CONFIG.QUEUE_RETRY_AFTER_SECONDS
        ),
    )
    return BulkReingestAccepted(
        collection_id=str(collection_id),
        count=result.enqueued,
        matched=result.matched,
        enqueued=result.enqueued,
        capped=result.capped,
        max_fanout=result.ceiling,
        skipped_in_flight=result.skipped_in_flight,
        skipped_not_replayable=result.skipped_not_replayable,
        jobs=result.handles,
    )


@router.post(
    "/{collection_id}/trace-payloads/purge",
    response_model=TracePurgeResult,
)
@auto_handle_errors
async def purge_collection_trace_payloads(
    collection_id: CollectionRef,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> TracePurgeResult:
    """
    Reclaim every stored full execution-trace payload of a collection's jobs (the heavy raw bytes).

    Frees the object-store space the opt-in ``trace_verbosity='full'`` tier accumulates under each
    job's ``trace/{job_id}/`` prefix, and clears the stage-event rows' references so nothing keeps
    advertising a payload that is gone. Only TERMINAL jobs are reclaimed: an in-flight
    (pending/running) job is skipped so the purge can never race that job's trace-finalize — its trace
    is reclaimed once the job terminates (a later purge or the retention GC). Idempotent: purging a
    collection that stored nothing is a clean no-op returning zeros, NOT a 404. Best-effort — a
    storage error is swallowed, so the call reports the counts and never surfaces a 500 for a partial
    store failure.

    Returns:
        TracePurgeResult: jobs considered + object-store objects deleted; 404 only when the
            collection itself does not exist.
    """
    # 1. The collection must exist — an unknown id is a 404 even though the purge itself is idempotent.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. require(WRITE) already collection-scopes the `collection_id` path param before this body
    #    runs (403 cross-tenant); restate it locally, mirroring the other collection routes.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 3. Best-effort purge across the collection's jobs (façade owns postgres+s3; never raises).
    purged_jobs, deleted_objects = await CONTEXT.database.trace_payloads.purge_for_collection(
        collection_id
    )
    CONTEXT.logger.info(
        f"Purged trace payloads for collection {collection_id}: "
        f"{purged_jobs} job(s), {deleted_objects} object(s)"
    )
    return TracePurgeResult(purged_jobs=purged_jobs, deleted_objects=deleted_objects)


__all__ = ["router"]
