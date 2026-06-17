# ====== Code Summary ======
# Search section: collection-wide weighted multi-field hybrid search,
# plus per-document search (same engine, pinned to one doc).

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.search.models import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from metadata import schema_field_dicts

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
@auto_handle_errors
async def search_collection(collection_id: uuid.UUID, body: SearchRequest) -> SearchResponse:
    """Weighted multi-field hybrid search over a collection (requires S6 + retrieval wired)."""
    # 1. Retrieval must be enabled — return empty result set rather than 503 so the UI degrades gracefully
    if CONTEXT.retrieval is None:
        return SearchResponse(
            collection_id=collection_id, query=body.query, total=0, results=[],
            note="Hybrid search not available — Qdrant is not reachable in this deployment.",
        )

    # 2. Resolve the collection's metadata schema (drives the per-field vectors + weights)
    metadata_fields = await _schema_fields(collection_id)

    # 3. Execute and shape the response
    async with CONTEXT.postgres.session() as session:
        results = await CONTEXT.retrieval.search(
            collection_name=str(collection_id), query=body.query, top_k=body.top_k,
            session=session, payload_filter=body.filters, metadata_fields=metadata_fields,
            weight_overrides=body.weights,
        )
    return _to_response(collection_id, body.query, results)


@router.post("/{document_id}/search", response_model=SearchResponse)
@auto_handle_errors
async def search_within_document(
    collection_id: uuid.UUID, document_id: uuid.UUID, body: SearchRequest
) -> SearchResponse:
    """Hybrid search restricted to a single document's chunks (same engine + a pinned filter)."""
    # 1. Retrieval enabled + document belongs to this collection
    if CONTEXT.retrieval is None:
        return SearchResponse(
            collection_id=collection_id, query=body.query, total=0, results=[],
            note="Hybrid search not available — Qdrant is not reachable in this deployment.",
        )
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None or doc.collection_id != collection_id:
        raise HTTPException(
            status_code=404, detail=f"Document {document_id} not found in collection {collection_id}."
        )

    # 2. Merge a document_id == {id} constraint into the caller's filter
    pinned = _pin_document(body.filters, document_id)

    # 3. Execute with the pinned filter
    metadata_fields = await _schema_fields(collection_id)
    async with CONTEXT.postgres.session() as session:
        results = await CONTEXT.retrieval.search(
            collection_name=str(collection_id), query=body.query, top_k=body.top_k,
            session=session, payload_filter=pinned, metadata_fields=metadata_fields,
            weight_overrides=body.weights,
        )
    return _to_response(collection_id, body.query, results)


# ─── Private helpers ─────────────────────────────────────────────────────────


async def _schema_fields(collection_id: uuid.UUID) -> list[dict[str, Any]]:
    """Load a collection's metadata schema (404 if missing) as plain dicts for the engine."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    # Single source of truth for the per-collection schema (shared with the discovery endpoint).
    return schema_field_dicts(collection.metadata_fields)


def _pin_document(filt: dict[str, Any] | None, document_id: uuid.UUID) -> dict[str, Any]:
    """Add a ``document_id == {id}`` condition to the must-clause of a filter (preserving it)."""
    pinned = dict(filt or {})
    must = list(pinned.get("must", []))
    must.append({"key": "document_id", "match": {"value": str(document_id)}})
    pinned["must"] = must
    return pinned


def _to_response(collection_id: uuid.UUID, query: str, results: list[Any]) -> SearchResponse:
    """Shape hydrated SearchResult objects into the API response."""
    return SearchResponse(
        collection_id=collection_id, query=query, total=len(results),
        results=[_item(r) for r in results],
    )


def _item(r: Any) -> SearchResultItem:
    """Map a SearchResult to its API item model."""
    return SearchResultItem(
        chunk_id=r.chunk_id, document_id=r.document_id, score=r.score, raw_text=r.raw_text,
        strategy=r.strategy, token_count=r.token_count, pages=r.pages, block_ids=r.block_ids,
    )
