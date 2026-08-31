# ====== Code Summary ======
# The corpus router — the POWER-GRID surface over one collection's documents at 10k–100k+ scale:
# a paginated, per-column filtered + sorted query, and three bulk operations (delete / set-enabled /
# reingest) that all take the ONE shared DocumentSelector (explicit ids XOR filter-minus-exclusions),
# so "select all matching, deselect a few, act on the rest" never enumerates ids client-side. Every
# route fails fast in the same order — collection exists (404), caller owns it (403), request is
# structurally valid (422) — BEFORE any spend or mutation. All logic lives in backend.libs.corpus and
# the Database façade; the router only orchestrates and shapes.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.corpus import (
    BulkDeleteResponse,
    BulkEnabledResponse,
    BulkReingestResponse,
    CorpusMapper,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentSelector,
    DocumentSelectorResolver,
)
from ...libs.reingest import BulkReingestService
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator

router = APIRouter(prefix="/collections", tags=["corpus"])


async def _require_scoped_collection(
    collection_id: uuid.UUID, principal: AuthPrincipal
) -> Collection:
    """Load a collection (404 unknown) and enforce the caller's collection scope (403 foreign)."""
    # 1. Existence first — an unknown collection is a 404 regardless of scope.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    # 2. The path-param gate already scoped this id; restate it locally for the body's mutations.
    AuthzGuard.assert_collection_scope(principal, str(collection_id))
    return collection


async def _resolve_targets(
    collection_id: uuid.UUID, selector: DocumentSelector, principal: AuthPrincipal
) -> list[uuid.UUID]:
    """The shared bulk gate: collection exists (404), caller owns it (403), selector resolves (422)."""
    # 1. Existence + scope before any resolution touches documents.
    await _require_scoped_collection(collection_id, principal)
    # 2. Resolve the selector against the schema; a bad field/op/id is a clean 422.
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    try:
        return await DocumentSelectorResolver(CONTEXT.database).resolve(
            collection_id, selector, schema
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{collection_id}/documents/query", response_model=DocumentQueryResponse)
@auto_handle_errors
async def query_documents(
    collection_id: uuid.UUID,
    request: DocumentQueryRequest,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> DocumentQueryResponse:
    """
    Return one filtered, sorted, paginated page of a collection's documents + the total match count.

    Each row carries the base catalogue fields plus a compact ``{field_name: value}`` map of the
    collection's document-metadata (bulk-loaded for the page — no N+1). ``limit`` is clamped to the
    server page ceiling. Read the metadata-column SCHEMA (names + types) from ``GET /collections/{id}``.

    Returns:
        DocumentQueryResponse: total + limit/offset echo + the page of rows; 404 unknown collection,
            422 on an unknown/non-filterable metadata field, a bad operator or an unknown sort field.
    """
    # 1. Existence + scope, then load the schema (resolves + validates every dynamic reference).
    await _require_scoped_collection(collection_id, principal)
    schema = await CONTEXT.database.collections.get_schema(collection_id)

    # 2. Validate + map the request to the framework-free spec (a bad field/op is a clean 422).
    try:
        spec = CorpusMapper.to_spec(request.filter, request.sort, schema)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 3. Clamp the page size, run the page + total under one set of predicates, bulk-load metadata.
    limit = min(request.pagination.limit, RUNTIME_CONFIG.CORPUS_MAX_PAGE_SIZE)
    documents, total = await CONTEXT.database.documents.query(
        collection_id, spec, limit, request.pagination.offset
    )
    metadata = await CONTEXT.database.documents.get_metadata_for_documents(
        [document.id for document in documents]
    )

    # 4. Shape each row with its resolved metadata map (field ids → names from the schema).
    names = {field.id: field.field_name for field in schema}
    rows = [
        CorpusMapper.grid_row(document, metadata.get(document.id, []), names)
        for document in documents
    ]
    return DocumentQueryResponse(
        total=total, limit=limit, offset=request.pagination.offset, rows=rows
    )


@router.post("/{collection_id}/documents/delete", response_model=BulkDeleteResponse)
@auto_handle_errors
async def bulk_delete(
    collection_id: uuid.UUID,
    selector: DocumentSelector,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> BulkDeleteResponse:
    """
    Delete every selected document everywhere (Qdrant points + PG cascade + orphan-only blob purge).

    Returns:
        BulkDeleteResponse: matched vs deleted; 404 unknown collection, 422 on a bad selector
            (unknown/foreign id, or an invalid filter field/operator).
    """
    # 1. Existence + scope, then resolve the selector to a concrete, collection-scoped id set (422).
    target_ids = await _resolve_targets(collection_id, selector, principal)

    # 2. Coherent cross-store bulk delete; report matched vs actually-deleted.
    deleted = await CONTEXT.database.documents.delete_many(target_ids)
    CONTEXT.logger.info(f"Bulk delete on {collection_id}: {deleted}/{len(target_ids)} removed")
    return BulkDeleteResponse(
        collection_id=str(collection_id), matched=len(target_ids), deleted=deleted
    )


@router.post("/{collection_id}/documents/set-enabled", response_model=BulkEnabledResponse)
@auto_handle_errors
async def bulk_set_enabled(
    collection_id: uuid.UUID,
    selector: DocumentSelector,
    enabled: bool,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> BulkEnabledResponse:
    """
    Enable or disable every selected document — a pure Postgres flag flip (no re-index, no Qdrant).

    ``enabled`` is a query parameter. A document toggle is read by search as a bounded exclusion, so
    a mass toggle never fans out to Qdrant and never implies a re-index.

    Returns:
        BulkEnabledResponse: matched vs updated (already-in-state rows skipped); 404 unknown
            collection, 422 on a bad selector.
    """
    # 1. Existence + scope, then resolve the selector to the concrete target id set (422).
    target_ids = await _resolve_targets(collection_id, selector, principal)

    # 2. One bulk flag flip; report matched vs actually-changed.
    updated = await CONTEXT.database.enablement.set_documents_enabled(target_ids, enabled)
    return BulkEnabledResponse(
        collection_id=str(collection_id),
        enabled=enabled,
        matched=len(target_ids),
        updated=updated,
        reindex_implied=False,
    )


@router.post(
    "/{collection_id}/documents/reingest", response_model=BulkReingestResponse, status_code=202
)
@auto_handle_errors
async def bulk_reingest(
    collection_id: uuid.UUID,
    selector: DocumentSelector,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> BulkReingestResponse:
    """
    Re-run the full pipeline over every selected document — one fresh job per document (poll each).

    Fail-fast: after the collection (404) + scope (403) gates, the stored pipeline is healed +
    structurally validated ONCE (422) before any job is minted, so a broken collection surfaces here
    instead of as N failed jobs. A filter selector matching MORE than the fan-out ceiling enqueues
    only the first N and reports ``capped=true`` with the full ``matched`` count.

    Returns:
        BulkReingestResponse: matched / enqueued / capped + one job handle per run (202); 404 unknown
            collection, 422 on a stale/broken pipeline or a bad selector.
    """
    # 1. Existence + scope.
    collection = await _require_scoped_collection(collection_id, principal)

    # 2. Fail-fast on a stale/broken pipeline BEFORE minting any job (heal, then structurally validate).
    try:
        pipeline_blob = BlobNormalizer.normalize(collection.pipeline)
    except BlobNormalizationError as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    PipelineBlobValidator.validate(pipeline_blob)

    # 3. Resolve the selector to the concrete target id set (422 on a bad selector).
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    try:
        matched = await DocumentSelectorResolver(CONTEXT.database).resolve(
            collection_id, selector, schema
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 4. Cap the fan-out — never silently flood the queue with 100k jobs on one call.
    ceiling = RUNTIME_CONFIG.CORPUS_MAX_REINGEST_FANOUT
    capped = len(matched) > ceiling
    targets = matched[:ceiling]
    if capped:
        CONTEXT.logger.warning(
            f"Bulk reingest on {collection_id}: {len(matched)} matched, capped to {ceiling}"
        )

    # 5. Fan out one full-pipeline job per resolved document.
    documents = await CONTEXT.database.documents.get_by_ids(targets)
    handles = await BulkReingestService(CONTEXT.database, CONTEXT.queue).enqueue(
        collection, documents
    )
    return BulkReingestResponse(
        collection_id=str(collection_id),
        matched=len(matched),
        enqueued=len(handles),
        capped=capped,
        max_fanout=ceiling,
        jobs=handles,
    )


__all__ = ["router"]
