# ====== Code Summary ======
# The collections router — the contract's CRUD: create (schema declared up front + pipeline
# blob seeded with the product default), read, patch the config blobs (pipeline VALIDATED
# before storage — a broken graph never reaches the worker), delete, plus the schema-driven
# discovery of the identity/limits contract. Every rejection carries an explicit HTTP code and a
# precise message. Non-route logic lives in helpers.py (pure) and store_sync.py (store follow-through).

# ====== Standard Library Imports ======
import json
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.blob_secrets import restore_blob_secrets
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer
from shared_libs.pipelines.ingest.estimate import CostEstimate
from shared_libs.public_models import SourceDocument
from shared_libs.services.db.facades import CollectionUpdateSpec, DuplicateCollectionNameError
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...libs.corpus import DocumentFilter, DocumentSelector, DocumentSelectorResolver
from ...libs.estimate import CollectionEstimateRequest, EstimateInputError
from ...libs.health import CollectionHealthResponse
from ...libs.logsafe import LogSafeHelpers
from ...libs.preview import (
    PreviewGraphError,
    PreviewInputError,
    PreviewResponse,
    PreviewSourceResolver,
)
from ...libs.reingest import BulkReingestAccepted, BulkReingestRequest, BulkReingestService
from ...utils.error_handling import auto_handle_errors
from ...utils.pipeline_validation import PipelineBlobValidator
from ...utils.upload_reader import UploadReader
from .blob_helpers import CollectionBlobHelpers
from .helpers import CollectionHelpers
from .models import (
    CollectionContractSchemaResponse,
    CollectionListItem,
    CollectionModel,
    CollectionStorageResponse,
    CreateCollectionRequest,
    PreviewJobAccepted,
    PreviewJobResult,
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

    # 4. Batch EVERY collection's schema in ONE query (no per-row ``get_schema`` N+1), then build each
    #    list row DIRECTLY from the row + its schema + summary — no to_model()→model_dump() re-splat,
    #    and masking skips the deepcopy for the secret-free stock blobs (_mask_for_list).
    schemas = await CONTEXT.database.collections.get_schemas_by_collections(ids)
    return [CollectionHelpers.to_list_item(c, schemas[c.id], summaries[c.id]) for c in collections]


@router.get(
    "/contract-schema",
    response_model=CollectionContractSchemaResponse,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def get_contract_schema() -> CollectionContractSchemaResponse:
    """
    Discover the FULL collection-contract vocabulary — nothing has to be guessed.

    Serves three things, each straight from the canonical server source it validates against (never a
    hand-copied literal): ``config_schema`` (the identity/limits scalar contract, mirroring a node's
    ``config_schema`` so a new scalar field auto-surfaces in the UI), ``field_schema`` (one metadata
    ``FieldSpec`` — its ``$defs`` carry the ``field_type``/``origin``/``scope`` enums), and
    ``supported_format_tokens`` (the accepted upload tokens). A purely-HTTP client (e.g. the MCP)
    thus learns every valid value from the API instead of discovering it was wrong at a 422.

    Returns:
        CollectionContractSchemaResponse: The identity/limits schema + the field/format vocabulary.
    """
    # 1. Every part is derived from the SAME models the create/upload path validates against — no drift.
    return CollectionHelpers.contract_schema()


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


def _parse_preview_blob(blob: str | None) -> dict | None:
    """Parse the optional candidate blob form field (a JSON object) — a 422 on malformed input."""
    # 1. No candidate → preview the collection's own stored pipeline (None tells the service so).
    if blob is None or blob.strip() == "":
        return None
    # 2. A present candidate must be a JSON object; anything else is a caller fault, not a 500.
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"blob is not valid JSON: {exc}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="blob must be a JSON object.")
    return parsed


@router.post(
    "/{collection_id}/pipeline/preview",
    response_model=PreviewResponse,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def preview_pipeline(
    request: Request,
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
    file: UploadFile | None = File(
        None, description="The document to dry-run (omit to use document_id)."
    ),
    document_id: str | None = Form(
        None, description="An existing document to dry-run (omit to upload)."
    ),
    blob: str | None = Form(
        None, description="Optional candidate pipeline blob (JSON) to preview."
    ),
    metadata: str = Form(
        "{}", description="Declared metadata for an UPLOADED source (JSON object)."
    ),
    max_chunks: int | None = Form(None, description="How many preview chunks to return (capped)."),
) -> PreviewResponse:
    """
    Dry-run the ingestion pipeline on ONE document and return a bounded preview — NOTHING is persisted.

    Runs the INGEST graph inline (the same pure engine a real run uses) against either an uploaded
    file OR an already-ingested ``document_id``, optionally with a candidate ``blob`` instead of the
    collection's stored pipeline. Returns an IR summary, the first N chunks, the run's ACTUAL metered
    cost, and the full execution trace. No document row, S3 object or Qdrant point is written. The run
    is bounded by the interactive guardrails (PREVIEW_RUN_TIMEOUT_SECONDS wall-clock cap + PREVIEW_MAX_BYTES
    body cap). A node that fails is DATA (ok=false + the trace showing where it died), never a 500.

    Returns:
        PreviewResponse: The bounded dry-run report (404 unknown collection/document; 422 on a bad
        blob, a missing/oversized source, or neither/both of file and document_id supplied).
    """
    # 1. The collection must exist and be in the caller's scope (WRITE — a preview consumes provider spend).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Exactly one source: an uploaded file XOR an existing document id.
    if (file is None) == (document_id is None):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of 'file' or 'document_id'."
        )

    # 3. Parse the optional candidate blob (JSON object) + resolve the chunk ceiling.
    blob_override = _parse_preview_blob(blob)
    ceiling = CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_CHUNKS
    effective_max_chunks = ceiling if max_chunks is None else max(0, min(max_chunks, ceiling))
    size_cap = min(collection.max_file_size_bytes, CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_BYTES)

    # 4. Build the SourceDocument: an uploaded body (read under the preview cap) or a rehydrated doc.
    try:
        source = await _resolve_preview_source(
            file, document_id, metadata, collection_id, collection, request, size_cap
        )
    except PreviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 5. Dry-run inline (no persistence). A bad blob is a 422; a failed node is DATA in the response.
    try:
        result = await CONTEXT.preview_service.preview(
            collection_id,
            source,
            max_chunks=effective_max_chunks,
            blob_override=blob_override,
            collection=collection,
        )
    except (PreviewGraphError, BlobNormalizationError) as exc:
        raise HTTPException(status_code=422, detail=f"Collection {collection_id}: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return result


async def _resolve_preview_source(
    file: UploadFile | None,
    document_id: str | None,
    metadata: str,
    collection_id: uuid.UUID,
    collection: Collection,
    request: Request,
    size_cap: int,
) -> SourceDocument:
    """
    Build the dry-run SourceDocument from an uploaded file or an existing document — reads only.

    Raises:
        HTTPException: 422 on a bad document id / metadata JSON; 404 on an unknown/foreign document.
        PreviewInputError: Oversized body or missing stored bytes (mapped to 422 by the caller).
    """
    # 1. Uploaded bytes: read under the preview size cap, no storage. Declared meta is optional JSON.
    if file is not None:
        UploadReader.reject_oversized_body(request, size_cap)
        content, _ = await UploadReader.read_capped(file, size_cap)
        try:
            declared = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
        if not isinstance(declared, dict):
            raise HTTPException(status_code=422, detail="metadata must be a JSON object.")
        return SourceDocument(
            filename=file.filename or "upload", content=content, declared_meta=declared
        )

    # 2. Existing document: it must exist AND belong to this collection (no cross-collection peek).
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"document_id '{document_id}' is not a valid UUID."
        )
    document = await CONTEXT.database.documents.get(doc_uuid)
    if document is None or document.collection_id != collection.id:
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found in collection {collection_id}.",
        )
    return await PreviewSourceResolver(CONTEXT.database).from_document(document, size_cap)


@router.post(
    "/{collection_id}/pipeline/preview/jobs",
    response_model=PreviewJobAccepted,
    status_code=202,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def submit_preview_job(
    request: Request,
    collection_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
    file: UploadFile | None = File(
        None, description="The document to dry-run (omit to use document_id)."
    ),
    document_id: str | None = Form(
        None, description="An existing document to dry-run (omit to upload)."
    ),
    blob: str | None = Form(
        None, description="Optional candidate pipeline blob (JSON) to preview."
    ),
    metadata: str = Form(
        "{}", description="Declared metadata for an UPLOADED source (JSON object)."
    ),
    max_chunks: int | None = Form(None, description="How many preview chunks to return (capped)."),
) -> PreviewJobAccepted:
    """
    Submit an ASYNCHRONOUS worker-side dry-run preview — returns a pollable id, persists NOTHING.

    Unlike the inline ``/pipeline/preview`` fast-lane (which runs in the API process and cannot parse
    pipelines whose deps — docling — live only in the worker image), this enqueues a WORKER preview
    job that runs the full ingest graph with every dependency present, so it covers ALL pipelines. The
    uploaded bytes (capped at PREVIEW_MAX_BYTES) ride through the queue; an existing ``document_id`` is
    rehydrated worker-side from the store. The worker writes nothing durable and RETURNS the bounded
    report as the job result (kept in Redis with a TTL). Poll ``/pipeline/preview/jobs/{preview_id}``.

    Returns:
        PreviewJobAccepted: The preview id + initial status (202); 404 unknown collection/document;
        422 on a bad blob, a missing/oversized source, or neither/both of file and document_id.
    """
    # 1. The collection must exist and be in the caller's scope (WRITE — a preview consumes spend).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Exactly one source: an uploaded file XOR an existing document id.
    if (file is None) == (document_id is None):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of 'file' or 'document_id'."
        )

    # 3. Parse the optional candidate blob (JSON object).
    blob_override = _parse_preview_blob(blob)
    size_cap = min(collection.max_file_size_bytes, CONTEXT.RUNTIME_CONFIG.PREVIEW_MAX_BYTES)

    # 4. Resolve the source payload carried to the worker: uploaded bytes read under the cap, OR an
    #    existing document id validated to exist in this collection (the worker rehydrates its bytes).
    content, declared, filename, resolved_document_id = await _resolve_preview_submission(
        file, document_id, metadata, collection, request, size_cap
    )

    # 5. Enqueue the worker preview job keyed by a fresh preview id, then return it for polling.
    preview_id = uuid.uuid4().hex
    await CONTEXT.queue.enqueue_preview(
        preview_id,
        str(collection_id),
        resolved_document_id,
        content,
        declared,
        filename,
        blob_override,
        max_chunks,
    )
    return PreviewJobAccepted(preview_id=preview_id, status="pending")


@router.get(
    "/{collection_id}/pipeline/preview/jobs/{preview_id}",
    response_model=PreviewJobResult,
    dependencies=[Depends(require(Capability.WRITE))],
)
@auto_handle_errors
async def get_preview_job(
    collection_id: uuid.UUID,
    preview_id: str,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> PreviewJobResult:
    """
    Poll an asynchronous dry-run preview by its id — the bounded report appears once status is 'done'.

    A failed NODE is DATA: status 'done' with ``result.ok`` = false (never a 500). 'failed' is reserved
    for the rare case the worker job itself crashed/timed out. An unknown or expired id is a 404.

    Returns:
        PreviewJobResult: status + (the report when done); 404 when the collection is out of scope or
        the preview id is unknown/expired.
    """
    # 1. Scope the collection (the id is in the path; a preview is a WRITE-scoped operation).
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    AuthzGuard.assert_collection_scope(principal, str(collection_id))

    # 2. Read the arq job state + result (the result is the PreviewResponse dict when complete).
    status, result, error = await CONTEXT.queue.get_preview_result(preview_id)
    if status == "not_found":
        raise HTTPException(status_code=404, detail=f"Preview {preview_id} not found or expired.")
    return PreviewJobResult(
        preview_id=preview_id,
        status=status,
        result=PreviewResponse(**result) if result is not None else None,
        error=error,
    )


async def _resolve_preview_submission(
    file: UploadFile | None,
    document_id: str | None,
    metadata: str,
    collection: Collection,
    request: Request,
    size_cap: int,
) -> tuple[bytes | None, dict, str, str | None]:
    """
    Resolve a worker-preview submission's payload: uploaded bytes OR a validated existing document id.

    For an uploaded file the bytes are read under the preview size cap and carried to the worker on the
    queue (no storage). For an existing document id, the document is validated to exist in THIS
    collection here (fail-fast 404 at submit) but its bytes are NOT read — the worker rehydrates them.

    Returns:
        tuple[bytes | None, dict, str, str | None]: (content | None, declared_meta, filename,
            document_id | None).

    Raises:
        HTTPException: 422 on a bad document id / metadata JSON / oversized body; 404 on an
            unknown/foreign document.
    """
    # 1. Uploaded bytes: read under the preview cap, no storage. Declared meta is optional JSON.
    if file is not None:
        UploadReader.reject_oversized_body(request, size_cap)
        content, _ = await UploadReader.read_capped(file, size_cap)
        try:
            declared = json.loads(metadata)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"metadata is not valid JSON: {exc}")
        if not isinstance(declared, dict):
            raise HTTPException(status_code=422, detail="metadata must be a JSON object.")
        return content, declared, file.filename or "upload", None

    # 2. Existing document: it must exist AND belong to this collection (no cross-collection peek).
    try:
        doc_uuid = uuid.UUID(str(document_id))
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"document_id '{document_id}' is not a valid UUID."
        )
    document = await CONTEXT.database.documents.get(doc_uuid)
    if document is None or document.collection_id != collection.id:
        raise HTTPException(
            status_code=404,
            detail=f"Document {document_id} not found in collection {collection.id}.",
        )
    return None, {}, document.filename, str(doc_uuid)


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

    # 1b. Resolve the SEARCH blob from its preset: the default (or omitted) keeps the {} stock-default
    #     sentinel; a non-default preset is a real search graph, validated exactly as an explicit one.
    search_blob = CollectionBlobHelpers.search_preset_blob(request.search_preset)
    if search_blob:
        CollectionHelpers.validate_search_blob(search_blob)

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
                trace_verbosity=request.trace_verbosity,
                pipeline=blob,
                search=search_blob,
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
                request.trace_verbosity,
            )
        ),
        name=request.name,
        supported_formats=request.supported_formats,
        tags=request.tags,
        max_file_size_bytes=request.max_file_size_bytes,
        job_timeout_seconds=request.job_timeout_seconds,
        trace_verbosity=request.trace_verbosity,
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
