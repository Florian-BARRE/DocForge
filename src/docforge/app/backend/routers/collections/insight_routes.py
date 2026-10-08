# ====== Code Summary ======
# Collection insight routes — the read-only, zero-spend operational views of one collection: the
# on-demand health probe, the agent-oriented describe guide, the storage footprint and the pre-hoc
# cost estimate. None of them enqueues a job or writes anything.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.ingest import BlobNormalizationError
from shared_libs.pipelines.ingest.estimate import CostEstimate

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import Capability, require
from ...libs.collection_ref import CollectionRef
from ...libs.describe import CollectionDescriber, CollectionDescription
from ...libs.estimate import CollectionEstimateRequest, EstimateInputError
from ...libs.health import CollectionHealthResponse
from ...utils.error_handling import auto_handle_errors
from .models import CollectionStorageResponse

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get(
    "/{collection_id}/health",
    response_model=CollectionHealthResponse,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def get_collection_health(collection_id: CollectionRef) -> CollectionHealthResponse:
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
    "/{collection_id}/describe",
    response_model=CollectionDescription,
    dependencies=[Depends(require(Capability.READ_TEXT))],
)
@auto_handle_errors
async def describe_collection(collection_id: CollectionRef) -> CollectionDescription:
    """
    Return a LEAN, agent-oriented guide to querying one collection — call it before searching.

    Fields (meaning, type, flags, real example values), the valid ``search_in`` targets, the filter
    grammar and ready-to-send example search bodies. No pipeline/search config, no secret.

    Returns:
        CollectionDescription: The guide (404 when the collection is unknown).
    """
    # 1. Compose the guide (read-only, bounded per-field value reads).
    description = await CollectionDescriber(CONTEXT.database).describe(collection_id)

    # 2. Unknown collection → 404, mirroring the other collection reads.
    if description is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return description


@router.get(
    "/{collection_id}/storage",
    response_model=CollectionStorageResponse,
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def get_collection_storage(collection_id: CollectionRef) -> CollectionStorageResponse:
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
    dependencies=[Depends(require(Capability.READ_TECHNICAL))],
)
@auto_handle_errors
async def estimate_collection(
    collection_id: CollectionRef,
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


__all__ = ["router"]
