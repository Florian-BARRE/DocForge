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
from fastapi import APIRouter, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...utils.error_handling import auto_handle_errors
from .helpers import ExplorerHelpers
from .models import ChunkInfo, DocumentDetail, DocumentListItem, PageInfo
from .models_ir import DocumentIRModel

router = APIRouter(tags=["explorer"])


async def _require_document(document_id: uuid.UUID):
    """Fetch a document or raise a 404 — the guard every document-scoped route shares."""
    document = await CONTEXT.database.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    return document


@router.get("/collections/{collection_id}/documents", response_model=list[DocumentListItem])
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
async def get_document(document_id: uuid.UUID) -> DocumentDetail:
    """
    Return one document's full facts and its resolved document-level metadata.

    Returns:
        DocumentDetail: Facts + metadata (field names joined from the schema); 404 when unknown.
    """
    # 1. The document (404 guard) — its collection scopes the schema lookup.
    document = await _require_document(document_id)

    # 2. Resolve field ids to names via the collection schema, then map the values.
    schema = await CONTEXT.database.collections.get_schema(document.collection_id)
    rows = await CONTEXT.database.documents.get_metadata(document_id)
    names = ExplorerHelpers.field_names(schema)
    return ExplorerHelpers.detail(document, ExplorerHelpers.metadata_values(rows, names))


@router.get("/documents/{document_id}/pages", response_model=list[PageInfo])
@auto_handle_errors
async def get_document_pages(document_id: uuid.UUID) -> list[PageInfo]:
    """
    Return a document's pages, in order — geometry, routing and the render blob reference.

    Returns:
        list[PageInfo]: One row per page; 404 when the document is unknown.
    """
    # 1. Existence first, then the ordered pages.
    await _require_document(document_id)
    pages = await CONTEXT.database.documents.get_pages(document_id)
    return [ExplorerHelpers.page(page) for page in pages]


@router.get("/documents/{document_id}/ir", response_model=DocumentIRModel)
@auto_handle_errors
async def get_document_ir(document_id: uuid.UUID) -> DocumentIRModel:
    """
    Return the document's FULL IR in one payload — blocks, tables, figures and enrichments.

    Returns:
        DocumentIRModel: The whole canonical IR (can be large); 404 when the document is unknown.
    """
    # 1. Existence first, then the whole IR bundle.
    await _require_document(document_id)
    bundle = await CONTEXT.database.documents.get_ir(document_id)
    return ExplorerHelpers.ir(bundle)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkInfo])
@auto_handle_errors
async def get_document_chunks(document_id: uuid.UUID) -> list[ChunkInfo]:
    """
    Return a document's chunks — enriched text, composition (block ids) and generated metadata.

    Returns:
        list[ChunkInfo]: One row per chunk, in order; 404 when the document is unknown.
    """
    # 1. The document (404 guard) — its collection scopes the field-name resolution.
    document = await _require_document(document_id)
    names = ExplorerHelpers.field_names(
        await CONTEXT.database.collections.get_schema(document.collection_id)
    )

    # 2. Chunks + their composition and metadata in bulk (three queries, no per-chunk N+1).
    chunks = await CONTEXT.database.documents.get_chunks(document_id)
    composition = await CONTEXT.database.documents.get_document_chunk_composition(document_id)
    metadata = await CONTEXT.database.documents.get_document_chunk_metadata(document_id)

    # 3. Group the child rows by chunk id (composition already ordered by position).
    blocks_by_chunk: dict[uuid.UUID, list[str]] = defaultdict(list)
    for link in composition:
        blocks_by_chunk[link.chunk_id].append(link.block_id)
    meta_by_chunk: dict[uuid.UUID, list] = defaultdict(list)
    for value in metadata:
        meta_by_chunk[value.chunk_id].append(value)

    # 4. Map each chunk with its grouped composition and resolved metadata.
    return [
        ExplorerHelpers.chunk(
            chunk,
            blocks_by_chunk[chunk.id],
            ExplorerHelpers.metadata_values(meta_by_chunk[chunk.id], names),
        )
        for chunk in chunks
    ]


@router.delete("/documents/{document_id}", status_code=204)
@auto_handle_errors
async def delete_document(document_id: uuid.UUID) -> None:
    """
    Delete a document everywhere (Qdrant points, PG cascade, orphan-only blob purge); 404 unknown.
    """
    # 1. The facade runs the coherent cross-store deletion; False means the id never existed.
    deleted = await CONTEXT.database.documents.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")
    CONTEXT.logger.info(f"Document {document_id} deleted")


__all__ = ["router"]
