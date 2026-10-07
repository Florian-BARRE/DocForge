# ====== Code Summary ======
# The search router — the retrieval READ path behind a collection. It stays the thin request-side
# gate (404 unknown collection · 409 no embed node · 422 non-filterable filter), then DELEGATES the
# actual retrieval to the graph-based search pipeline via CONTEXT.search_service (the graph embeds
# the query with the collection's own embedder and runs the hybrid fusion + hydration). The router
# keeps the filterability gate (the graph trusts the filters it is handed), resolves string-ish filter
# values to their stored spelling (Postgres is the value oracle — case-insensitive filters + "did you
# mean" hints), then flattens the graph's Hits and the filter hints into the client response — projected
# to the request's return_fields (served with response_model_exclude_unset, so an omitted field is
# ABSENT from the hit, not null) and, with group_by="document", capped per document by the service.
# Per-request tuning (min_score, rerank skip/require, fusion override, debug scores) rides through the
# service as a SearchTuning; a rerank=true request on a graph with no rerank stage is a 422.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.auth import Capability, require
from ...libs.metrics.search_health import SearchHealthReader
from ...libs.search import (
    HitProjection,
    MinScoreHint,
    QueryEmbedderProbe,
    ScoreKindClassifier,
    SearchCollectionSpecs,
    SearchRetrievalProbe,
    SearchRunError,
    SearchRunTimeout,
    SearchTargetValidator,
    SearchTuning,
    SearchTuningError,
    SearchUnavailableError,
    TermlessQueryHint,
    ZeroHitHintBuilder,
)
from ...utils.error_handling import auto_handle_errors
from .encode_failure import EncodeFailureMapper
from .filter_gate import SearchFilterGate
from .hit_mapper import SearchHitMapper
from .model_mapper import SearchModelMapper
from .models import (
    SearchCostModel,
    SearchHealthSummary,
    SearchRequest,
    SearchResponse,
)

router = APIRouter(tags=["search"])


@router.get(
    "/search/health",
    response_model=SearchHealthSummary,
    dependencies=[Depends(require(Capability.READ))],
)
@auto_handle_errors
async def search_health() -> SearchHealthSummary:
    """
    Return a compact search-runtime health summary for the deployment Overview cockpit.

    Search runs INLINE in the request (no job/fleet surface of its own), so this mirrors the
    operational tiles ``GET /jobs/queue`` and ``GET /jobs/workers/live`` power. Every figure is
    CUMULATIVE since process start, read straight off the in-process ``docforge_search_*`` Prometheus
    series (the same source Grafana scrapes — no parallel counters). The payload carries no per-tenant
    data or ids: it is a process-global aggregate, gated by the READ capability like the other read
    routes. Trends/rates over time stay in Grafana; this is the at-a-glance snapshot.

    Returns:
        SearchHealthSummary: Total runs, error rate, p95 latency, zero-result rate and mean hits.
    """
    # 1. Fold the current search series into the tile — no I/O, just reads the in-process collectors.
    return SearchHealthReader.summary()


@router.post(
    "/collections/{collection_id}/search",
    response_model=SearchResponse,
    # A return_fields projection leaves the unrequested hit fields UNSET so they are absent from the
    # wire (not null); the full (default) response sets every field explicitly, so it is unchanged.
    response_model_exclude_unset=True,
    dependencies=[Depends(require(Capability.SEARCH))],
)
@auto_handle_errors
async def search_collection(collection_id: uuid.UUID, request: SearchRequest) -> SearchResponse:
    """
    Run a hybrid search over a collection and return ranked, hydrated chunk hits.

    Delegates retrieval to the graph-based search pipeline (CONTEXT.search_service); the router
    stays the request-side gate and diagnostic layer.

    Returns:
        SearchResponse: The echoed query, its hits (best first) and any filter hints. 404 when the
        collection is unknown, 409 when it has no embedder wired, 422 when a filter names a
        non-filterable field, a value outside a field's enum, or an empty/oversized value list,
        when return_fields names an unknown hit field, or when rerank=true but the collection's
        search pipeline has no rerank stage.
    """
    # 0. Parse the hit-field projection first — a typo'd field name is a caller error, rejected
    #    before any read or spend.
    allowed_fields = SearchHitMapper.projectable_fields()
    projection, unknown_fields = HitProjection.from_request(request.return_fields, allowed_fields)
    if unknown_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown return_fields {unknown_fields} — allowed: {allowed_fields} or "
            f"'metadata.<field>'.",
        )
    tuning = SearchTuning(
        min_score=request.min_score,
        rerank=request.rerank,
        fusion=request.fusion,
        debug=request.debug,
    )

    # 1. The collection must exist — everything (its embedder, its schema) derives from it.
    collection = await CONTEXT.database.collections.get(collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail=f"Collection {collection_id} not found.")

    # 2. Locate the collection's embed node — without it there are no vectors to search.
    embed_blob = SearchCollectionSpecs.embed_node_blob(collection.pipeline)
    if embed_blob is None:
        raise HTTPException(
            status_code=409, detail="Collection has no embed node — search is unavailable."
        )

    # 3. Stay the filter gate — the graph trusts the filters it is handed, so an invalid filter is
    #    rejected 422 BEFORE the service is invoked; string-ish values are then resolved against the
    #    stored values (case-insensitive canonical spelling + "did you mean" hints). Shared with the
    #    browse route, so both accept exactly the same filter maps.
    schema = await CONTEXT.database.collections.get_schema(collection_id)
    resolution = await SearchFilterGate.resolve(request.filters, schema)

    # 4. Gate the search targets the same way — a target naming a field/vector the collection never
    #    indexed (or a selection with no modality) is a caller error rejected 422 before any spend.
    #    A flag set in Postgres is not enough: the vector must also be declared by the Qdrant store.
    #    The store's declared vectors are read (one Qdrant call) only when a metadata field is targeted.
    search_targets = SearchModelMapper.to_search_targets(request.search_in)
    declared = (
        await CONTEXT.database.index_state.declared_vectors(collection_id)
        if SearchTargetValidator.needs_store_check(search_targets)
        else None
    )
    target_errors = SearchTargetValidator.validate_search_targets(search_targets, schema, declared)
    if target_errors:
        raise HTTPException(status_code=422, detail=f"Invalid search target(s): {target_errors}")
    # 4b. A metadata-only search skips the (body-scoring) rerank — before the score_kind is derived.
    tuning = tuning.for_targets(search_targets)

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
    probe = SearchRetrievalProbe()
    try:
        result, usage = await CONTEXT.search_service.search(
            collection_id,
            request.query,
            top_k=request.limit,
            filters=resolution.filters if request.filters is not None else None,
            search_targets=search_targets,
            collection=collection,
            text_fields=resolution.text_fields,
            title_field=SearchCollectionSpecs.title_field_spec(collection, schema),
            projection=projection,
            max_per_document=request.max_per_document if request.group_by else None,
            tuning=tuning,
            probe=probe,
        )
    except SearchTuningError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except SearchRunTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "search_timeout", "detail": f"Search timed out. ({exc})"},
        )
    except SearchUnavailableError as exc:
        # The encode failed — probe the query embedder to classify permanent vs transient (bounded
        # by the sweep's own ~5s per-probe cap; it spends no real call, only preflight()).
        status = await QueryEmbedderProbe().classify(collection.pipeline)
        raise EncodeFailureMapper.encode_failure_http(status, str(exc))
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
    #    The metered search-time LLM spend (rewrite/HyDE) rides ``cost`` — None when no paid call ran.
    #    Filter hints = the early "no stored value" ones + the zero-hit "likely culprit" ones (+ a
    #    min_score cut that emptied the answer, + a lexical target the query had no term for).
    prompt_tokens, completion_tokens, cost_usd, call_count = usage
    cost = (
        SearchCostModel(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            call_count=call_count,
        )
        if call_count > 0
        else None
    )
    # The filter-culprit hints must judge the filters on what they LET THROUGH — before the
    # min_score cut — or a threshold that dropped every hit would be blamed on a valid filter.
    min_score_cut = (result.debug or {}).get("min_score") or {}
    pre_cut_count = len(result.hits) + int(min_score_cut.get("dropped") or 0)
    hints = (
        resolution.hints
        + ZeroHitHintBuilder.build(resolution, pre_cut_count)
        + MinScoreHint.build(min_score_cut, len(result.hits))
        + TermlessQueryHint.build(probe, request.query)
    )
    #    Hits are projected to return_fields and, on a debug search, carry their fusion/rerank
    #    scores; score_kind names what the TUNED run delivered (a skipped rerank → its fusion kind,
    #    or the raw vector score when the retrieval queried a single vector — no fusion ran).
    hits = SearchHitMapper.map(result.hits, projection, debug=tuning.debug)
    score_kind = tuning.score_kind(
        ScoreKindClassifier.score_kind(
            collection.search, rerank_degraded=ScoreKindClassifier.rerank_degraded(result.debug)
        ),
        ScoreKindClassifier.score_kind(collection.search, rerank_degraded=True),
        ScoreKindClassifier.raw_kind(probe.raw_axis()),
    )
    return SearchResponse(
        query=request.query,
        hits=hits,
        score_kind=score_kind,
        cost=cost,
        debug_info=result.debug,
        hints=[SearchModelMapper.to_hint_model(hint) for hint in hints],
    )


__all__ = ["router"]
