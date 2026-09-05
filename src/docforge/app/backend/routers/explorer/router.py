# ====== Code Summary ======
# The document explorer router — the pure-READ surface behind a collection (the admission WRITE path
# lives in the documents router; this one only browses and removes). It exposes, with explicit full
# paths (no router prefix, so it can own both /collections/{id}/documents and /documents/{id}/...):
# the catalogue list, one document's facts + resolved metadata, its pages, its full IR, its chunks,
# and the coherent cross-store delete. Every unknown id is an explicit 404.

# ====== Standard Library Imports ======
import uuid
from collections import defaultdict

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException, Query, Response

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
from ..jobs.models import JobEvent
from .helpers import ExplorerHelpers
from .models import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    PageInfo,
)
from .models_ir import DocumentIRModel, DocumentProvenance
from .views import DocumentViewHelpers

router = APIRouter(tags=["explorer"])


async def _require_document(document_id: uuid.UUID, principal: AuthPrincipal):
    """Fetch a document (404 unknown) then enforce the caller's collection scope (403 foreign).

    The collection is not in the path here, so the path-scope gate cannot see it — every
    document-keyed route funnels through this guard to close the cross-tenant read gap. Full-access
    keys no-op inside the helper, so root and AUTH_ENABLED=false are unaffected.
    """
    # 1. Existence first — an unknown id is a 404 regardless of scope.
    document = await CONTEXT.database.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    # 2. Scope the read/write by the document's own collection.
    AuthzGuard.assert_collection_scope(principal, str(document.collection_id))
    return document


async def _assert_chunk_scope(chunk_ids: list[uuid.UUID], principal: AuthPrincipal) -> None:
    """Enforce that the caller owns every collection the target chunks belong to (no-op for root).

    A scoped key may mutate a chunk only through a collection it owns; a chunk in any foreign
    collection fails the whole request with 403. Unknown ids resolve to no collection and are left
    for the handler's own not-found reporting.
    """
    # 1. Full access bypasses scoping (skip the lookup entirely).
    if principal.is_full_access:
        return

    # 2. Every distinct owning collection of the targeted chunks must be in the key's scope.
    collections = await CONTEXT.database.documents.collections_for_chunks(chunk_ids)
    for collection_id in collections:
        AuthzGuard.assert_collection_scope(principal, collection_id)


@router.get(
    "/collections/{collection_id}/documents",
    response_model=list[DocumentListItem],
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def list_documents(
    collection_id: uuid.UUID,
    limit: int = Query(
        default=RUNTIME_CONFIG.CORPUS_MAX_PAGE_SIZE,
        ge=1,
        description="Max documents to return (clamped to the server page ceiling). Returning exactly "
        "this many signals more may exist — page with 'offset' (or use the corpus grid for filtering).",
    ),
    offset: int = Query(
        default=0, ge=0, description="Documents to skip (paging; 0 = the first page)."
    ),
) -> list[DocumentListItem]:
    """
    Return one bounded page of a collection's documents, newest first — the browse catalogue.

    Bounded to avoid loading a 100k-document collection into memory in one call: ``limit`` is clamped
    to the server page ceiling and defaults to it, and ``offset`` pages the id-stabilised order. For
    filtered/sorted access at scale, use the corpus grid (``POST /collections/{id}/documents/query``).

    Returns:
        list[DocumentListItem]: One row per document (at most ``limit``); 404 when the collection is
        unknown.
    """
    # 1. The collection must exist — an empty list would otherwise hide a bad id.
    if await CONTEXT.database.collections.get(collection_id) is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Clamp the page size to the server ceiling, then read one bounded page.
    bounded_limit = min(limit, RUNTIME_CONFIG.CORPUS_MAX_PAGE_SIZE)
    documents = await CONTEXT.database.documents.list_for_collection(
        collection_id, limit=bounded_limit, offset=offset
    )
    return [ExplorerHelpers.list_item(document) for document in documents]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
@auto_handle_errors
async def get_document(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> DocumentDetail:
    """
    Return one document's full facts and its resolved document-level metadata.

    Returns:
        DocumentDetail: Facts + metadata (field names joined from the schema); 404 when unknown.
    """
    # 1. The document (404 guard + collection-scope gate) — its collection scopes the schema lookup.
    document = await _require_document(document_id, principal)

    # 2. Resolve field ids to names via the collection schema, then map the values.
    schema = await CONTEXT.database.collections.get_schema(document.collection_id)
    rows = await CONTEXT.database.documents.get_metadata(document_id)
    names = ExplorerHelpers.field_names(schema)
    return ExplorerHelpers.detail(document, ExplorerHelpers.metadata_values(rows, names))


@router.get("/documents/{document_id}/pages", response_model=list[PageInfo])
@auto_handle_errors
async def get_document_pages(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> list[PageInfo]:
    """
    Return a document's pages, in order — geometry, routing and the render blob reference.

    Returns:
        list[PageInfo]: One row per page; 404 when the document is unknown.
    """
    # 1. Existence + scope guard, then the ordered pages.
    await _require_document(document_id, principal)
    pages = await CONTEXT.database.documents.get_pages(document_id)
    return [ExplorerHelpers.page(page) for page in pages]


@router.get("/documents/{document_id}/ir", response_model=DocumentIRModel)
@auto_handle_errors
async def get_document_ir(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> DocumentIRModel:
    """
    Return the document's FULL IR in one payload — blocks, tables, figures and enrichments.

    Returns:
        DocumentIRModel: The whole canonical IR (can be large); 404 when the document is unknown.
    """
    # 1. Existence + scope guard, then the whole IR bundle.
    await _require_document(document_id, principal)
    bundle = await CONTEXT.database.documents.get_ir(document_id)
    return ExplorerHelpers.ir(bundle)


@router.get("/documents/{document_id}/provenance", response_model=DocumentProvenance)
@auto_handle_errors
async def get_document_provenance(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> DocumentProvenance:
    """
    Return a document's ingestion provenance — the parser/model pipeline that produced its IR + chunks.

    The provenance IS the last SUCCESSFUL ingestion job's per-stage trace (which parser/model ran at
    each stage, with timing and any token/cost). It is keyed on the latest DONE run — the one that
    actually produced the IR/chunks on display — so a later FAILED or still-running re-ingest never
    shadows it with a run that yielded nothing. When no successful run survives (only failures, or the
    completed job was reaped/expired), ``available`` is False and ``stages`` is empty — the IR still
    stands, only its run timeline could not be recovered.

    Returns:
        DocumentProvenance: The pipeline version and the ordered stage trace; 404 when unknown.
    """
    # 1. Existence + scope guard, then the document's most recent SUCCESSFUL ingestion job (the run
    #    that produced the current persisted IR — never a later FAILED run that produced nothing).
    document = await _require_document(document_id, principal)
    job = await CONTEXT.database.jobs.get_latest_successful_for_document(document_id)

    # 2. When a job survives, fold its stage-event rows into the ordered trace.
    stages: list[JobEvent] = []
    if job is not None:
        events = await CONTEXT.database.jobs.list_events(job.id)
        stages = [JobEvent.from_row(event) for event in events]

    # 3. Assemble the provenance envelope (available=False when no job row remained).
    return DocumentProvenance(
        document_id=str(document_id),
        pipeline_version=document.pipeline_version,
        job_id=None if job is None else str(job.id),
        available=job is not None,
        stages=stages,
    )


@router.get("/documents/{document_id}/markdown", response_class=Response)
@auto_handle_errors
async def get_document_markdown(
    document_id: uuid.UUID,
    download: bool = Query(
        False, description="When true, return an attachment download instead of an inline view."
    ),
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> Response:
    """
    Render the document as an on-the-fly markdown VIEW generated from the canonical IR.

    Args:
        document_id (uuid.UUID): The document to render.
        download (bool): Attach a ``Content-Disposition`` (``<stem>.md``) instead of rendering inline.

    Returns:
        Response: ``text/markdown; charset=utf-8``; 404 when the document is unknown.
    """
    # 1. Existence + scope guard, then the stored IR rows.
    document = await _require_document(document_id, principal)
    bundle = await CONTEXT.database.documents.get_ir(document_id)

    # 2. Adapt the rows to a DocumentIR, linearize, and wrap (inline or attachment).
    return DocumentViewHelpers.markdown(document, bundle, download)


@router.get("/documents/{document_id}/html", response_class=Response)
@auto_handle_errors
async def get_document_html(
    document_id: uuid.UUID,
    download: bool = Query(
        False, description="When true, return an attachment download instead of an inline view."
    ),
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> Response:
    """
    Render the document as an on-the-fly HTML VIEW generated from the canonical IR.

    Args:
        document_id (uuid.UUID): The document to render.
        download (bool): Attach a ``Content-Disposition`` (``<stem>.html``) instead of rendering inline.

    Returns:
        Response: ``text/html; charset=utf-8``; 404 when the document is unknown.
    """
    # 1. Existence + scope guard, then the stored IR rows.
    document = await _require_document(document_id, principal)
    bundle = await CONTEXT.database.documents.get_ir(document_id)

    # 2. Adapt the rows to a DocumentIR, linearize, and wrap (inline or attachment).
    return DocumentViewHelpers.html(document, bundle, download)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkInfo])
@auto_handle_errors
async def get_document_chunks(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.READ)),
) -> list[ChunkInfo]:
    """
    Return a document's chunks — enriched text, composition (block ids) and generated metadata.

    Returns:
        list[ChunkInfo]: One row per chunk, in order; 404 when the document is unknown.
    """
    # 1. The document (404 guard + scope gate) — its collection scopes the field-name resolution.
    document = await _require_document(document_id, principal)
    names = ExplorerHelpers.field_names(
        await CONTEXT.database.collections.get_schema(document.collection_id)
    )

    # 2. Chunks + their composition and metadata in bulk (three queries, no per-chunk N+1).
    chunks = await CONTEXT.database.documents.get_chunks(document_id)
    composition = await CONTEXT.database.documents.get_document_chunk_composition(document_id)
    metadata = await CONTEXT.database.documents.get_document_chunk_metadata(document_id)

    # 3. Resolve each chunk's page from its primary (leading) block in ONE bulk query — the same
    #    location read search-hit hydration uses, so the two surfaces agree on the page.
    locations = await CONTEXT.database.documents.get_block_locations_for_chunks(
        [chunk.id for chunk in chunks]
    )

    # 4. Group the child rows by chunk id (composition already ordered by position).
    blocks_by_chunk: dict[uuid.UUID, list[str]] = defaultdict(list)
    for link in composition:
        blocks_by_chunk[link.chunk_id].append(link.block_id)
    meta_by_chunk: dict[uuid.UUID, list] = defaultdict(list)
    for value in metadata:
        meta_by_chunk[value.chunk_id].append(value)

    # 5. Map each chunk with its grouped composition, resolved metadata and primary-block page (the
    #    first entry per chunk is its leading block, so its page is the chunk's page).
    return [
        ExplorerHelpers.chunk(
            chunk,
            blocks_by_chunk[chunk.id],
            ExplorerHelpers.metadata_values(meta_by_chunk[chunk.id], names),
            page=(located[0]["page"] if (located := locations.get(str(chunk.id))) else None),
        )
        for chunk in chunks
    ]


@router.patch("/chunks/{chunk_id}/enabled", response_model=ChunkEnabledResult)
@auto_handle_errors
async def set_chunk_enabled(
    chunk_id: uuid.UUID,
    patch: ChunkEnabledPatch,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> ChunkEnabledResult:
    """
    Toggle one chunk's searchability (reversible, no re-embed).

    Sets the chunk's enabled_override; the facade recomputes the effective state and flips the
    chunk's Qdrant point payload. A chunk that was never embedded has no point to flip and comes
    back with reindex_required=True (it stays non-searchable until a later on-demand embed).

    Returns:
        ChunkEnabledResult: The recomputed state + reindex flag; 404 when the chunk is unknown.
    """
    # 1. Scope the mutation by the chunk's owning collection (403 for a foreign scoped key).
    await _assert_chunk_scope([chunk_id], principal)

    # 2. The facade toggles the (single) chunk; an empty result means the id never existed.
    outcomes = await CONTEXT.database.enablement.set_chunks_enabled([chunk_id], patch.enabled)
    if not outcomes:
        raise HTTPException(status_code=404, detail=f"Chunk {chunk_id} not found.")

    # 3. Shape the single outcome.
    return ExplorerHelpers.chunk_toggle(outcomes[0])


@router.patch("/chunks/enabled", response_model=BulkChunkEnabledResponse)
@auto_handle_errors
async def set_chunks_enabled(
    patch: BulkChunkEnabledPatch,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> BulkChunkEnabledResponse:
    """
    Toggle several chunks' searchability to the same state in one call (the UI multi-select).

    Unknown ids are reported in ``not_found`` rather than failing the whole request; each known
    chunk carries its own reindex_required flag (a never-embedded chunk being enabled).

    Returns:
        BulkChunkEnabledResponse: The per-chunk outcomes plus the ids that matched no chunk.
    """
    # 1. Scope the mutation — a scoped key may not touch a chunk in a collection it does not own.
    await _assert_chunk_scope(patch.chunk_ids, principal)

    # 2. Toggle all requested chunks in one facade call.
    outcomes = await CONTEXT.database.enablement.set_chunks_enabled(patch.chunk_ids, patch.enabled)

    # 3. The ids that resolved to no chunk (requested minus returned).
    found = {outcome.chunk_id for outcome in outcomes}
    not_found = [str(chunk_id) for chunk_id in patch.chunk_ids if chunk_id not in found]

    # 4. Shape the per-chunk outcomes and the gap.
    return BulkChunkEnabledResponse(
        results=[ExplorerHelpers.chunk_toggle(outcome) for outcome in outcomes],
        not_found=not_found,
    )


@router.delete("/documents/{document_id}", status_code=204)
@auto_handle_errors
async def delete_document(
    document_id: uuid.UUID,
    principal: AuthPrincipal = Depends(require(Capability.WRITE)),
) -> None:
    """
    Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge); 404 unknown.
    """
    # 1. Load + scope-gate the document first (404 unknown, 403 for a foreign scoped key) so a
    #    scoped key can never delete across tenants.
    await _require_document(document_id, principal)

    # 2. The facade runs the coherent cross-store deletion; False means the id never existed.
    deleted = await CONTEXT.database.documents.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    CONTEXT.logger.info(f"Document {document_id} deleted")


__all__ = ["router"]
