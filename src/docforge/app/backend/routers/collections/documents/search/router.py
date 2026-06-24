# ====== Code Summary ======
# Search section: collection-wide weighted multi-field hybrid search,
# plus per-document search (same engine, pinned to one doc).
# Requests go through SearchPipelineEngine.
# The embed provider is auto-derived from collection pipeline.embed.chain[0].

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
import httpx
from fastapi import APIRouter, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.search.builder import build_search_pipeline
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.collections.documents.search.models import (
    SearchGroupItem,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from common_libs.domain.metadata import schema_field_dicts

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
@auto_handle_errors
async def search_collection(collection_id: uuid.UUID, body: SearchRequest) -> SearchResponse:
    """Weighted multi-field hybrid search over a collection."""
    # 1. Retrieval must be enabled
    if CONTEXT.retrieval is None:
        return SearchResponse(
            collection_id=collection_id, query=body.query, total=0, results=[],
            note="Hybrid search not available — Qdrant is not reachable in this deployment.",
        )

    # 2. Fetch the collection once
    collection = await _get_collection(collection_id)
    metadata_fields = _extract_schema_fields(collection)

    # 3. Build search pipeline from collection pipeline config.
    # Embed provider is derived from pipeline.embed.chain[0] so query vectors
    # match the indexed vectors -- mixing providers corrupts results.
    try:
        search_pipeline = build_search_pipeline(
            collection.pipeline, CONTEXT.retrieval, CONTEXT.RUNTIME_CONFIG
        )
    except ValueError as exc:
        # 503 — the collection's configured search/embed provider could not be built.
        CONTEXT.logger.warning(
            f"Search rejected (503 provider not configured): collection={collection_id} error={exc}"
        )
        raise HTTPException(
            status_code=503,
            detail=f"Search pipeline provider not configured for this collection — {exc}",
        )

    # 4. Execute -- debug path exposes per-vector ranks
    try:
        async with CONTEXT.postgres.session() as session:
            if body.debug:
                debug_data = await search_pipeline.run_debug(
                    query=body.query, top_k=body.top_k, session=session,
                    collection_name=str(collection_id), payload_filter=body.filters,
                    metadata_fields=metadata_fields, weight_overrides=body.weights,
                )
                return _to_response_debug(collection_id, body.query, debug_data)

            outcome = await search_pipeline.run(
                query=body.query, top_k=body.top_k, session=session,
                collection_name=str(collection_id), payload_filter=body.filters,
                metadata_fields=metadata_fields, weight_overrides=body.weights,
            )
        return _to_response(collection_id, body.query, outcome)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # 503 — embedding / Qdrant backend unreachable (connection refused or timed out).
        CONTEXT.logger.warning(
            f"Search rejected (503 embed/qdrant unreachable): collection={collection_id} error={exc}"
        )
        raise HTTPException(
            status_code=503,
            detail=f"Embedding service unreachable — {exc}.",
        )


@router.post("/{document_id}/search", response_model=SearchResponse)
@auto_handle_errors
async def search_within_document(
    collection_id: uuid.UUID, document_id: uuid.UUID, body: SearchRequest
) -> SearchResponse:
    """Hybrid search restricted to a single document's chunks."""
    # 1. Retrieval enabled + document belongs to this collection
    if CONTEXT.retrieval is None:
        return SearchResponse(
            collection_id=collection_id, query=body.query, total=0, results=[],
            note="Hybrid search not available — Qdrant is not reachable in this deployment.",
        )
    async with CONTEXT.postgres.session() as session:
        doc = await CONTEXT.document_repo.get_by_id(session, document_id)
    if doc is None or doc.collection_id != collection_id:
        # 404 — document id is unknown OR belongs to a different collection (scope mismatch).
        CONTEXT.logger.warning(
            f"In-document search rejected (404): document={document_id} collection={collection_id}"
        )
        raise HTTPException(
            status_code=404, detail=f"Document {document_id} not found in collection {collection_id}."
        )

    # 2. Merge a document_id == {id} constraint into the caller filter
    pinned = _pin_document(body.filters, document_id)

    # 3. Fetch collection for schema fields + search pipeline resolution
    collection = await _get_collection(collection_id)
    metadata_fields = _extract_schema_fields(collection)
    try:
        search_pipeline = build_search_pipeline(
            collection.pipeline, CONTEXT.retrieval, CONTEXT.RUNTIME_CONFIG
        )
    except ValueError as exc:
        # 503 — the collection's configured search/embed provider could not be built.
        CONTEXT.logger.warning(
            f"In-document search rejected (503 provider not configured): collection={collection_id} "
            f"document={document_id} error={exc}"
        )
        raise HTTPException(
            status_code=503,
            detail=f"Search pipeline provider not configured — {exc}",
        )

    # 4. Execute with pinned filter + collection-specific search pipeline
    try:
        async with CONTEXT.postgres.session() as session:
            if body.debug:
                debug_data = await search_pipeline.run_debug(
                    query=body.query, top_k=body.top_k, session=session,
                    collection_name=str(collection_id), payload_filter=pinned,
                    metadata_fields=metadata_fields, weight_overrides=body.weights,
                )
                return _to_response_debug(collection_id, body.query, debug_data)

            outcome = await search_pipeline.run(
                query=body.query, top_k=body.top_k, session=session,
                collection_name=str(collection_id), payload_filter=pinned,
                metadata_fields=metadata_fields, weight_overrides=body.weights,
            )
        return _to_response(collection_id, body.query, outcome)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        # 503 — embedding / Qdrant backend unreachable (connection refused or timed out).
        CONTEXT.logger.warning(
            f"In-document search rejected (503 embed/qdrant unreachable): collection={collection_id} "
            f"document={document_id} error={exc}"
        )
        raise HTTPException(
            status_code=503,
            detail=f"Embedding service unreachable — {exc}.",
        )


# --- Private helpers ---------------------------------------------------------


async def _get_collection(collection_id: uuid.UUID) -> Any:
    """Fetch the collection ORM object (404 if missing)."""
    async with CONTEXT.postgres.session() as session:
        collection = await CONTEXT.collection_repo.get_by_id(session, collection_id)
    if collection is None:
        # 404 — search target collection does not exist.
        CONTEXT.logger.warning(f"Search rejected (404 unknown collection): collection={collection_id}")
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")
    return collection


def _extract_schema_fields(collection: Any) -> list[dict[str, Any]]:
    """Extract the metadata schema as plain dicts."""
    return schema_field_dicts(collection.metadata_fields)


def _pin_document(filt: dict[str, Any] | None, document_id: uuid.UUID) -> dict[str, Any]:
    """Add a document_id == {id} condition to the must-clause of a filter."""
    pinned = dict(filt or {})
    must = list(pinned.get("must", []))
    must.append({"key": "document_id", "match": {"value": str(document_id)}})
    pinned["must"] = must
    return pinned


def _to_response(collection_id: uuid.UUID, query: str, outcome: Any) -> SearchResponse:
    """
    Shape a SearchOutcome (flat results + optional document groups) into the API response.

    Args:
        collection_id (uuid.UUID): Target collection.
        query (str): Original query string.
        outcome (Any): SearchOutcome with ``.results`` and optional ``.groups``.

    Returns:
        SearchResponse: Flat items plus document groups when grouping was enabled.
    """
    results = getattr(outcome, "results", outcome)
    groups = getattr(outcome, "groups", None)
    return SearchResponse(
        collection_id=collection_id, query=query, total=len(results),
        results=[_item(r) for r in results],
        groups=_groups(groups),
    )


def _groups(groups: list[Any] | None) -> list[SearchGroupItem] | None:
    """Map engine DocumentGroup objects to API group items (None stays None)."""
    if groups is None:
        return None
    return [
        SearchGroupItem(
            document_id=g.document_id, score=g.score,
            chunks=[_item(c) for c in g.chunks],
        )
        for g in groups
    ]


def _to_response_debug(
    collection_id: uuid.UUID, query: str, debug_data: dict[str, Any]
) -> SearchResponse:
    """
    Shape debug search data (with per-vector ranks) into the API response.

    Builds a reverse-lookup table from ranked (vector to ordered chunk IDs)
    so each result item carries vector_ranks.

    Args:
        collection_id (uuid.UUID): Target collection.
        query (str): Original query string.
        debug_data (dict): Output of SearchPipelineEngine.run_debug().

    Returns:
        SearchResponse: Results enriched with vector rank breakdown and debug_info.
    """
    ranked: dict[str, list[str]] = debug_data.get("ranked", {})
    resolved: dict[str, Any] = debug_data.get("resolved", {})
    results: list[Any] = debug_data.get("results", [])
    groups: list[Any] | None = debug_data.get("groups")
    pipeline_meta: dict[str, Any] = debug_data.get("pipeline", {})

    # 1. Build reverse lookup: chunk_id -> vector_name -> 1-indexed rank
    rank_map: dict[str, dict[str, int]] = {}
    for vector_name, chunk_ids in ranked.items():
        for rank_zero, chunk_id in enumerate(chunk_ids):
            rank_map.setdefault(chunk_id, {})[vector_name] = rank_zero + 1

    # 2. Attach per-vector ranks to each result item
    items = [
        SearchResultItem(
            chunk_id=r.chunk_id, document_id=r.document_id, score=r.score,
            raw_text=r.raw_text, strategy=r.strategy, token_count=r.token_count,
            pages=r.pages, block_ids=r.block_ids,
            vector_ranks=rank_map.get(r.chunk_id),
        )
        for r in results
    ]

    # 3. Merge pipeline metadata into debug_info for observability
    debug_info = {**resolved, **pipeline_meta}

    return SearchResponse(
        collection_id=collection_id, query=query, total=len(items), results=items,
        groups=_groups(groups),
        note=_sparse_note(resolved),
        debug_info=debug_info,
    )


def _sparse_note(resolved: dict[str, Any]) -> str | None:
    """
    Warn when keyword/BM25 search was requested but the embed provider is dense-only.

    A dense-only embed provider (e.g. OpenAI) yields no sparse query vector, so sparse and
    hybrid modes silently lose their BM25 contribution.  Surfacing a note turns the silent
    degradation into actionable feedback.

    Args:
        resolved (dict): The retrieval plan (carries vector_mode + sparse_enabled).

    Returns:
        str | None: A guidance note, or None when sparse is either unused or available.
    """
    mode = resolved.get("vector_mode", "hybrid")
    if mode in ("sparse", "hybrid") and resolved.get("sparse_enabled") is False:
        return (
            "Keyword/BM25 search is inactive: the collection's embed provider is dense-only "
            "and produces no sparse vectors. Switch the embed stage to TEI (BGE-M3) and reindex "
            "to enable sparse/hybrid keyword matching."
        )
    return None


def _item(r: Any) -> SearchResultItem:
    """Map a SearchResult to its API item model."""
    return SearchResultItem(
        chunk_id=r.chunk_id, document_id=r.document_id, score=r.score, raw_text=r.raw_text,
        strategy=r.strategy, token_count=r.token_count, pages=r.pages, block_ids=r.block_ids,
    )

