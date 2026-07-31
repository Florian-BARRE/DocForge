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
from fastapi import APIRouter, Depends, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability, require
from ...utils.error_handling import auto_handle_errors
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
from .models_ir import DocumentIRModel

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
async def list_documents(collection_id: uuid.UUID) -> list[DocumentListItem]:
    """
    Return a collection's documents, newest first — the browse catalogue.

    Returns:
        list[DocumentListItem]: One row per document; 404 when the collection is unknown.
    """
    # 1. The collection must exist — an empty list would otherwise hide a bad id.
    if await CONTEXT.database.collections.get(collection_id) is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Straight read — map each row to its list item.
    documents = await CONTEXT.database.documents.list_for_collection(collection_id)
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
