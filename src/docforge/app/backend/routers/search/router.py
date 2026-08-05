# ====== Code Summary ======
# The search router — the retrieval READ path behind a collection. It stays the thin request-side
# gate (404 unknown collection · 409 no embed node · 422 non-filterable filter), then DELEGATES the
# actual retrieval to the graph-based search pipeline via CONTEXT.search_service (the graph embeds
# the query with the collection's own embedder and runs the hybrid fusion + hydration). The router
# keeps the filterability gate (the graph trusts the filters it is handed), then flattens the graph's
# Hits into the client response.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import Capability, require
from ...libs.search import (
    QueryEmbedderProbe,
    SearchRunError,
    SearchRunTimeout,
    SearchUnavailableError,
)
from ...utils.error_handling import auto_handle_errors
from .helpers import SearchHelpers
from .models import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post(
    "/collections/{collection_id}/search",
    response_model=SearchResponse,
    dependencies=[Depends(require(Capability.SEARCH))],
)
@auto_handle_errors
async def search_collection(collection_id: uuid.UUID, request: SearchRequest) -> SearchResponse:
    """
    Run a hybrid search over a collection and return ranked, hydrated chunk hits.

    Delegates retrieval to the graph-based search pipeline (CONTEXT.search_service); the router
    stays the request-side gate and diagnostic layer.

    Returns:
        SearchResponse: The echoed query and its hits, best first. 404 when the collection is
        unknown, 409 when it has no embedder wired, 422 when a filter names a non-filterable field.
    """
    # 1. The collection must exist — everything (its embedder, its schema) derives from it.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Locate the collection's embed node — without it there are no vectors to search.
    embed_blob = SearchHelpers.embed_node_blob(collection.pipeline)
    if embed_blob is None:
        raise HTTPException(
            status_code=409, detail="Collection has no embed node — search is unavailable."
        )

    # 3. Stay the filterability gate — the graph trusts the filters it is handed, so a filter that
    #    names a non-filterable field is rejected 422 BEFORE the service is invoked.
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    _, invalid = SearchHelpers.build_conditions(request.filters, schema)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Not a filterable field for this collection: {sorted(invalid)}",
        )

    # 3b. A filterable ENUM field only accepts its declared members — a value outside the enum is a
    #     caller error rejected 422 (else it silently returns 0 hits and reads as "nothing matches").
    enum_errors = SearchHelpers.enum_violations(request.filters, schema)
    if enum_errors:
        raise HTTPException(status_code=422, detail=f"Invalid filter value(s): {enum_errors}")

    # 4. Gate the search targets the same way — a target naming a field/vector the collection never
    #    indexed (or a selection with no modality) is a caller error rejected 422 before any spend.
    target_errors = SearchHelpers.validate_search_targets(request.search_in, schema)
    if target_errors:
        raise HTTPException(status_code=422, detail=f"Invalid search target(s): {target_errors}")

    # 5. Delegate the retrieval to the graph-based search pipeline. The failure classes are mapped
    #    distinctly so the caller can tell "retry shortly" from "fix your config":
    #      - SearchRunTimeout      → 504 {search_timeout} (the run blew its wall-clock cap)
    #      - SearchUnavailableError→ the query could not be encoded; a targeted, bounded probe of the
    #        collection's OWN query embedder then classifies it: a dead host / rejected key is a
    #        PERMANENT 424 (embedder_unreachable / embedder_auth_failed), a still-answering embedder
    #        means the failure was genuinely transient → 503 embedder_overloaded.
    #      - SearchRunError        → 422 (a genuinely invalid stored graph — re-save its blob)
    #    The subclasses are caught FIRST (Python matches except clauses in order), so only a real
    #    build/validate/output-contract failure keeps the alarming "invalid search graph" message.
    try:
        result = await CONTEXT.search_service.search(
            collection_id,
            request.query,
            top_k=request.limit,
            filters=request.filters,
            search_targets=SearchHelpers.to_search_targets(request.search_in),
            collection=collection,
        )
    except SearchRunTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "search_timeout", "detail": f"Search timed out. ({exc})"},
        )
    except SearchUnavailableError as exc:
        # The encode failed — probe the query embedder to classify permanent vs transient (bounded
        # by the sweep's own ~5s per-probe cap; it spends no real call, only preflight()).
        status = await QueryEmbedderProbe().classify(collection.pipeline)
        raise SearchHelpers.encode_failure_http(status, str(exc))
    except SearchRunError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"The collection's stored search graph is invalid — re-save its search "
            f"blob. ({exc})",
        )

    # 6. Shape the flat, client-facing response from the graph's Hits. The run's debug bag is
    #    surfaced as debug_info so a DEGRADED search (an encode axis was dropped — the note the
    #    pipeline threads through SearchResult.debug["degraded"]) is visible to the client instead of
    #    silently returning partial results. A healthy run carries only a minimal bag (hit count).
    return SearchResponse(
        query=request.query,
        hits=[SearchHelpers.to_hit_model(hit) for hit in result.hits],
        debug_info=result.debug,
    )


__all__ = ["router"]
