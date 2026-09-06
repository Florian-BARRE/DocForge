"""Search router: the query-to-hits wiring with the graph-based search pipeline mocked out at the
CONTEXT.search_service seam. Asserts the route stays the request-side gate (404 / 409 / 422 ladder),
resolves the query knobs, DELEGATES retrieval to the search service with the right arguments, and
flattens the graph's Hits (chunk_index/token_count lifted out of Hit.metadata) into the client
response. No network, no live stack, no hand-rolled facade retrieval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.public_models import FieldType
from shared_libs.public_models.search import Hit, SearchResult


# A minimal pipeline blob carrying one embed action node (bge_server, sparse on).
def _pipeline_with_embed() -> dict:
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {
                "node_type": "action",
                "id": "embed",
                "family": "embed",
                "kind": "bge_server",
                "config": {"model": "BAAI/bge-m3", "base_url": "http://bge:8008"},
            }
        ],
        "transitions": [],
        "bindings": {},
    }


def _schema() -> list:
    """A filterable keyword field ('topic'), a non-filterable one ('note'), a filterable ENUM, and
    the range-typed fields ('year' INTEGER, 'published' DATETIME) the range-filter tests use."""
    return [
        SimpleNamespace(field_name="topic", filterable=True, field_type=FieldType.STRING),
        SimpleNamespace(field_name="note", filterable=False, field_type=FieldType.STRING),
        SimpleNamespace(
            field_name="doc_type",
            filterable=True,
            field_type=FieldType.ENUM,
            enum_values=["policy", "contract"],
        ),
        SimpleNamespace(field_name="year", filterable=True, field_type=FieldType.INTEGER),
        SimpleNamespace(field_name="published", filterable=True, field_type=FieldType.DATETIME),
    ]


def _result(query: str) -> SearchResult:
    """A one-hit SearchResult; chunk_index/token_count ride in Hit.metadata (as the graph emits)."""
    return SearchResult(
        query=query,
        hits=[
            Hit(
                chunk_id="11111111-1111-1111-1111-000000000001",
                document_id="22222222-2222-2222-2222-222222222222",
                score=0.42,
                rank=1,
                text="chunk text 1",
                metadata={
                    "chunk_index": 3,
                    "token_count": 42,
                    "heading_path": ["Chapter II", "Article 5 — Principles"],
                    "filename": "gdpr.pdf",
                    "document_title": "EU Regulation",
                    "document_metadata": {"jurisdiction": "EU", "article_ref": "Article 5"},
                },
            )
        ],
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection reads + the search service; return the captured search() mock."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    # The service returns (SearchResult, usage-tuple); a stock search runs no paid LLM → count 0.
    search = AsyncMock(side_effect=lambda _cid, query, **_kw: (_result(query), (0, 0, None, 0)))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return search


def test_search_route_is_registered(fastapi_app) -> None:
    """The search route must be part of the API contract (POST under the collection scope)."""
    paths = fastapi_app.openapi()["paths"]
    assert "post" in paths["/api/v1/collections/{collection_id}/search"]


def test_search_delegates_to_service_and_shapes_hits(client, wired) -> None:
    """Happy path: the service is called with resolved knobs, and the graph Hit is flattened."""
    # 1. A query with a scalar filter on the filterable field.
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work", "limit": 5, "filters": {"topic": "ai"}},
    )
    assert response.status_code == 200, response.text

    # 2. Retrieval was delegated to the search service with the resolved arguments.
    kwargs = wired.await_args.kwargs
    assert wired.await_args.args[1] == "how does it work"
    assert kwargs["top_k"] == 5
    assert kwargs["filters"] == {"topic": "ai"}

    # 3. The hit is the flat view of the graph Hit (index/tokens lifted out of metadata).
    hit = response.json()["hits"][0]
    assert hit["chunk_id"] == "11111111-1111-1111-1111-000000000001"
    assert hit["document_id"] == "22222222-2222-2222-2222-222222222222"
    assert hit["score"] == 0.42
    assert hit["text"] == "chunk text 1"
    assert hit["chunk_index"] == 3
    assert hit["token_count"] == 42
    # 4. The hit self-cites: source identity + declared metadata are lifted out of the bag so the
    #    client never needs a second GET /documents/{id}.
    assert hit["filename"] == "gdpr.pdf"
    assert hit["document_title"] == "EU Regulation"
    assert hit["metadata"] == {"jurisdiction": "EU", "article_ref": "Article 5"}
    # 5. The section ancestry rides on the hit so a compliance result self-cites the clause.
    assert hit["heading_path"] == ["Chapter II", "Article 5 — Principles"]


def test_search_stock_run_reports_no_cost(client, wired) -> None:
    """A stock search that makes no paid LLM call (usage count 0) surfaces ``cost`` as null — never a
    fabricated 0 — so the client can tell "free run" from "priced run"."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["cost"] is None


def test_search_surfaces_the_metered_llm_cost(client, monkeypatch) -> None:
    """When the run makes a paid query-side LLM call (rewrite/HyDE), its priced usage is surfaced on
    the response ``cost`` (audit 539) — tokens + USD, from the service's summed meter."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    # The service reports one paid call: 100 in / 50 out, priced at $0.0003.
    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(side_effect=lambda _cid, query, **_kw: (_result(query), (100, 50, 0.0003, 1))),
    )

    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work"},
    )
    assert response.status_code == 200, response.text
    cost = response.json()["cost"]
    assert cost == {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "cost_usd": 0.0003,
        "call_count": 1,
    }


def test_search_passes_list_filter_verbatim(client, wired) -> None:
    """A list filter value reaches the service unchanged — the graph trusts the filter map."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"topic": ["ai", "ml"]}},
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {"topic": ["ai", "ml"]}


def test_search_passes_numeric_range_filter_verbatim(client, wired) -> None:
    """A numeric range on a range-typed field reaches the service unchanged (the graph builds the
    Qdrant Range) — a 200, with the range map threaded through untouched."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"year": {"gte": 2020, "lte": 2024}}},
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {"year": {"gte": 2020, "lte": 2024}}


def test_search_passes_datetime_range_filter_verbatim(client, wired) -> None:
    """A datetime range (ISO bounds) on a DATETIME field flows through to the service unchanged."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={
            "query": "q",
            "filters": {"published": {"gte": "2024-01-01", "lte": "2024-12-31"}},
        },
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {
        "published": {"gte": "2024-01-01", "lte": "2024-12-31"}
    }


def test_search_mixed_match_and_range_filter_passes(client, wired) -> None:
    """A scalar match and a range in the same filter map both flow through (200)."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"topic": "ai", "year": {"gt": 2019}}},
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {"topic": "ai", "year": {"gt": 2019}}


def test_search_range_on_non_range_typed_field_is_422(client, wired) -> None:
    """A range on a keyword field is a caller error rejected 422 before the service is invoked —
    Qdrant cannot range a keyword index."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"topic": {"gte": "a"}}},
    )
    assert response.status_code == 422, response.text
    assert "not range-typed" in response.text
    wired.assert_not_awaited()


def test_search_malformed_range_is_422(client, wired) -> None:
    """A malformed range (an unsupported bound key) is a 422, never a 500."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"year": {"between": 3}}},
    )
    assert response.status_code == 422, response.text
    assert "range" in response.text.lower()
    wired.assert_not_awaited()


def test_search_datetime_bounds_on_numeric_field_is_422(client, wired) -> None:
    """An ISO-string range on an INTEGER field is rejected 422 — the bound kind must match the
    field's declared type (a numeric field needs numeric bounds)."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"year": {"gte": "2024-01-01"}}},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_non_filterable_field_is_422(client, wired) -> None:
    """A filter on a non-filterable field is rejected before the service is invoked."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"note": "x"}},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_enum_filter_outside_the_declared_values_is_422(client, wired) -> None:
    """A filter value outside a field's declared enum is rejected 422 (not a silent 0-hit 200) —
    parity with upload-time enum validation, so a typo'd filter never reads as 'nothing matches'."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"doc_type": "newspaper"}},
    )
    assert response.status_code == 422, response.text
    # The message names the field and its allowed values.
    assert "doc_type" in response.text and "policy" in response.text
    wired.assert_not_awaited()


def test_search_enum_filter_within_the_declared_values_passes(client, wired) -> None:
    """A valid enum filter value flows through to the service unchanged (200)."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q", "filters": {"doc_type": "policy"}},
    )
    assert response.status_code == 200, response.text
    assert wired.await_args.kwargs["filters"] == {"doc_type": "policy"}


def test_search_blank_query_is_422(client, wired) -> None:
    """A whitespace-only query is rejected before it reaches the service."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "   "},
    )
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def test_search_unknown_collection_is_404(client, fastapi_app, monkeypatch) -> None:
    """An unknown collection id is an explicit 404."""
    from backend.context import CONTEXT

    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=None))
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 404, response.text


def test_search_invalid_stored_graph_is_422_not_500(client, wired, monkeypatch) -> None:
    """A stored search graph that the runner rejects (SearchRunError) is mapped to a clean 422 at
    the HTTP boundary — never a 500 with a traceback."""
    from backend.context import CONTEXT
    from backend.libs.search import SearchRunError

    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(side_effect=SearchRunError("final node produced RankedHits")),
    )
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    # 1. The invalid stored graph surfaces as a 422 naming the stored search graph, not a 500.
    assert response.status_code == 422, response.text
    assert "stored search graph is invalid" in response.text


def test_read_port_hydrate_threads_heading_path_onto_the_hit(fastapi_app) -> None:
    """CollectionReadPortImpl.hydrate lifts the chunk row's section ancestry into the Hit metadata
    bag (coalescing a NULL to an empty list), so the router can surface it for clause-level self-cite."""
    import asyncio
    import uuid as _uuid

    from backend.libs.search import CollectionReadPortImpl

    chunk_uuid = _uuid.uuid4()
    doc_uuid = _uuid.uuid4()
    chunk_row = SimpleNamespace(
        id=chunk_uuid,
        document_id=doc_uuid,
        text="Audit rights.",
        chunk_index=7,
        token_count=12,
        heading_path=["Article 7 — Audit rights"],
    )
    document = SimpleNamespace(id=doc_uuid, filename="charter.pdf", title="Charter")
    database = SimpleNamespace(
        documents=SimpleNamespace(
            get_chunks_by_ids=AsyncMock(return_value=[chunk_row]),
            get_by_ids=AsyncMock(return_value=[document]),
            get_filterable_metadata_for_documents=AsyncMock(return_value={doc_uuid: {}}),
            get_block_locations_for_chunks=AsyncMock(return_value={}),
        )
    )
    port = CollectionReadPortImpl(database, _uuid.uuid4())
    hydrated = asyncio.run(port.hydrate([str(chunk_uuid)]))

    hit = hydrated[str(chunk_uuid)]
    assert hit.metadata["heading_path"] == ["Article 7 — Audit rights"]

    # A NULL heading_path (rows predating the column) coalesces to an empty list, never None.
    chunk_row.heading_path = None
    hydrated = asyncio.run(port.hydrate([str(chunk_uuid)]))
    assert hydrated[str(chunk_uuid)].metadata["heading_path"] == []


def test_read_port_hydrate_threads_block_location_onto_the_hit(fastapi_app) -> None:
    """CollectionReadPortImpl.hydrate lifts each chunk's source-block location (block_ids + the
    per-block page/bbox, and the primary block's page/bbox) into the Hit metadata bag, so a UI can
    draw a box on the page. The bbox is the block's normalised [0, 1] box, carried verbatim."""
    import asyncio
    import uuid as _uuid

    from backend.libs.search import CollectionReadPortImpl
    from backend.routers.search.helpers import SearchHelpers

    chunk_uuid = _uuid.uuid4()
    doc_uuid = _uuid.uuid4()
    chunk_row = SimpleNamespace(
        id=chunk_uuid,
        document_id=doc_uuid,
        text="Audit rights.",
        chunk_index=7,
        token_count=12,
        heading_path=[],
    )
    document = SimpleNamespace(id=doc_uuid, filename="charter.pdf", title="Charter")
    # Two source blocks — the first (assembly order) is the chunk's primary block.
    locations = {
        str(chunk_uuid): [
            {"block_id": "doc:#/texts/3", "page": 2, "bbox": [0.1, 0.2, 0.5, 0.3]},
            {"block_id": "doc:#/texts/4", "page": 2, "bbox": [0.1, 0.35, 0.5, 0.4]},
        ]
    }
    database = SimpleNamespace(
        documents=SimpleNamespace(
            get_chunks_by_ids=AsyncMock(return_value=[chunk_row]),
            get_by_ids=AsyncMock(return_value=[document]),
            get_filterable_metadata_for_documents=AsyncMock(return_value={doc_uuid: {}}),
            get_block_locations_for_chunks=AsyncMock(return_value=locations),
        )
    )
    port = CollectionReadPortImpl(database, _uuid.uuid4())
    hit = asyncio.run(port.hydrate([str(chunk_uuid)]))[str(chunk_uuid)]

    # 1. The location rides in the metadata bag: block ids, primary page/bbox, and per-block list.
    assert hit.metadata["block_ids"] == ["doc:#/texts/3", "doc:#/texts/4"]
    assert hit.metadata["page"] == 2
    assert hit.metadata["bbox"] == [0.1, 0.2, 0.5, 0.3]
    assert hit.metadata["block_locations"] == [
        {"page": 2, "bbox": [0.1, 0.2, 0.5, 0.3]},
        {"page": 2, "bbox": [0.1, 0.35, 0.5, 0.4]},
    ]

    # 2. The flat client model surfaces it (the router flattens Hit → SearchHitModel).
    model = SearchHelpers.to_hit_model(hit)
    assert model.block_ids == ["doc:#/texts/3", "doc:#/texts/4"]
    assert model.page == 2 and model.bbox == [0.1, 0.2, 0.5, 0.3]
    assert [(loc.page, loc.bbox) for loc in model.block_locations] == [
        (2, [0.1, 0.2, 0.5, 0.3]),
        (2, [0.1, 0.35, 0.5, 0.4]),
    ]

    # 3. A chunk with no located blocks degrades cleanly (empty list, null primary).
    database.documents.get_block_locations_for_chunks = AsyncMock(return_value={})
    bare = asyncio.run(port.hydrate([str(chunk_uuid)]))[str(chunk_uuid)]
    assert bare.metadata["block_ids"] == [] and bare.metadata["page"] is None
    assert SearchHelpers.to_hit_model(bare).block_locations == []


def test_search_surfaces_degraded_note_in_debug_info(client, fastapi_app, monkeypatch) -> None:
    """A DEGRADED search (an encode axis was dropped — the pipeline threads the note into
    SearchResult.debug['degraded']) reaches the client via SearchResponse.debug_info, so a
    lexical-only answer is never silently returned as if it were full hybrid."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    monkeypatch.setattr(
        CONTEXT.database.collections, "get_schema", AsyncMock(return_value=_schema())
    )
    degraded = SearchResult(
        query="q",
        hits=[Hit(chunk_id="c1", document_id="d1", score=0.8, rank=1, text="t", metadata={})],
        debug={
            "hit_count": 1,
            "degraded": "semantic unavailable — embedder busy, lexical-only results",
        },
    )
    monkeypatch.setattr(
        CONTEXT.search_service, "search", AsyncMock(return_value=(degraded, (0, 0, None, 0)))
    )

    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 200, response.text
    debug_info = response.json()["debug_info"]
    assert debug_info is not None
    assert debug_info["degraded"] == "semantic unavailable — embedder busy, lexical-only results"


def test_healthy_search_leaves_debug_info_without_a_degraded_note(client, wired) -> None:
    """A healthy full-hybrid search carries no 'degraded' note — the mocked service returns a result
    with no debug bag, so debug_info stays null (nothing alarming surfaced on the happy path)."""
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "how does it work"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["debug_info"] is None


def test_pageless_block_location_surfaces_null_page(fastapi_app) -> None:
    """A page-less document's block location carries page=None all the way into the flat hit model —
    None means 'no page', distinct from a genuine 0-based page index 0 (which is preserved)."""
    from backend.routers.search.helpers import SearchHelpers

    pageless = Hit(
        chunk_id="c1",
        document_id="d1",
        score=0.5,
        rank=1,
        text="t",
        metadata={
            "page": None,
            "bbox": [0.1, 0.2, 0.5, 0.3],
            "block_locations": [{"page": None, "bbox": [0.1, 0.2, 0.5, 0.3]}],
        },
    )
    model = SearchHelpers.to_hit_model(pageless)
    assert model.page is None
    assert model.block_locations[0].page is None

    # A genuine page 0 (0-based first page of a paged doc) is NOT nulled — it is a real location.
    paged = Hit(
        chunk_id="c2",
        document_id="d1",
        score=0.4,
        rank=2,
        text="t",
        metadata={
            "page": 0,
            "bbox": [0, 0, 1, 1],
            "block_locations": [{"page": 0, "bbox": [0, 0, 1, 1]}],
        },
    )
    paged_model = SearchHelpers.to_hit_model(paged)
    assert paged_model.page == 0
    assert paged_model.block_locations[0].page == 0


def test_transient_error_messages_stay_honest_and_pin_the_contract(
    client, wired, monkeypatch
) -> None:
    """Guard the USER-FACING error contract so a refactor can't silently regress it: a run
    TimeoutError → 504 ``search_timeout``, a probed-transient encode failure → 503
    ``embedder_overloaded``, a probed-permanent encode failure → 424 ``embedder_unreachable``, and
    only a GENUINE invalid blob → 422 'invalid search graph'. None of the encode-failure codes are
    ever 422 — the classifier tells "fix your config" (424) from "retry shortly" (503)."""
    from backend.context import CONTEXT
    from backend.libs.search import (
        QueryEmbedderProbe,
        SearchRunError,
        SearchRunTimeout,
        SearchUnavailableError,
    )
    from shared_libs.pipelines.reachability import ProbeStatus

    cases = [
        (SearchRunTimeout("pipeline exceeded 30.0s"), None, 504, "search_timeout"),
        (
            SearchUnavailableError("QueryEncodeError: embedder saturated"),
            ProbeStatus.OK,
            503,
            "embedder_overloaded",
        ),
        (
            SearchUnavailableError("connection refused"),
            ProbeStatus.UNREACHABLE,
            424,
            "embedder_unreachable",
        ),
        (SearchRunError("final node produced RankedHits"), None, 422, None),
    ]
    for exc, probe_status, status, code in cases:
        monkeypatch.setattr(CONTEXT.search_service, "search", AsyncMock(side_effect=exc))
        if probe_status is not None:
            monkeypatch.setattr(
                QueryEmbedderProbe, "classify", AsyncMock(return_value=probe_status)
            )
        response = client.post(
            "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
            json={"query": "q"},
        )
        assert response.status_code == status, (exc, response.text)
        detail = response.json()["detail"]
        if code is None:
            # The genuinely invalid stored graph keeps its plain-string alarming message.
            assert "invalid" in detail.lower() and "search graph" in detail.lower()
        else:
            assert detail["code"] == code, (exc, detail)


def test_search_run_timeout_is_504_not_422(client, wired, monkeypatch) -> None:
    """A run that blew its wall-clock cap (SearchRunTimeout) is a RETRYABLE 504 ``search_timeout`` —
    never the alarming 422 'invalid search graph' (the graph is fine, the provider stuck)."""
    from backend.context import CONTEXT
    from backend.libs.search import SearchRunTimeout

    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(side_effect=SearchRunTimeout("search run timed out: pipeline exceeded 30.0s")),
    )
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 504, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "search_timeout"
    assert "timed out" in detail["detail"].lower()
    assert "invalid" not in response.text.lower()  # never mislabelled as an invalid graph


def test_search_embedder_unavailable_is_503_not_422(client, wired, monkeypatch) -> None:
    """A run that failed because the query could not be encoded (SearchUnavailableError) is
    classified by the bounded query-embedder probe; a still-answering embedder (probe → ok) means
    the failure was genuinely transient → a RETRYABLE 503 ``embedder_overloaded`` — never the
    invalid-graph 422."""
    from backend.context import CONTEXT
    from backend.libs.search import QueryEmbedderProbe, SearchUnavailableError
    from shared_libs.pipelines.reachability import ProbeStatus

    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(
            side_effect=SearchUnavailableError(
                "search temporarily unavailable: encode (collection): QueryEncodeError: ..."
            )
        ),
    )
    monkeypatch.setattr(QueryEmbedderProbe, "classify", AsyncMock(return_value=ProbeStatus.OK))
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 503, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "embedder_overloaded"
    assert "invalid" not in response.text.lower()


def test_search_embedder_permanent_failure_is_424_not_503(client, wired, monkeypatch) -> None:
    """A run that failed to encode because the embedder is genuinely unreachable (probe →
    unreachable) is a PERMANENT 424 ``embedder_unreachable`` — not the retryable 503, and not 422."""
    from backend.context import CONTEXT
    from backend.libs.search import QueryEmbedderProbe, SearchUnavailableError
    from shared_libs.pipelines.reachability import ProbeStatus

    monkeypatch.setattr(
        CONTEXT.search_service,
        "search",
        AsyncMock(side_effect=SearchUnavailableError("QueryEncodeError: connection refused")),
    )
    monkeypatch.setattr(
        QueryEmbedderProbe, "classify", AsyncMock(return_value=ProbeStatus.UNREACHABLE)
    )
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 424, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "embedder_unreachable"


def test_target_resolver_drops_empty_dense_axis_for_lexical_only(fastapi_app) -> None:
    """A degraded encode leaves EncodedQuery.dense empty; the resolver must NOT send an empty dense
    vector to the store — it drops the semantic axis and queries the surviving sparse (lexical) one."""
    from backend.libs.search.target_resolver import TargetVectorResolver
    from shared_libs.public_models.embed import SparseVector
    from shared_libs.public_models.search import EncodedQuery, default_content_targets

    encoded = EncodedQuery(
        dense=[],  # dense axis unavailable (embedder busy)
        sparse=SparseVector(indices=[7], values=[1.0]),
        model="fake",
        degraded="semantic unavailable — embedder busy, lexical-only results",
    )
    dense, sparse = TargetVectorResolver.resolve(encoded, default_content_targets())
    assert dense == {}  # no empty dense vector sent to the store
    assert sparse is not None  # lexical axis still queried


def test_search_no_embed_node_is_409(client, fastapi_app, monkeypatch) -> None:
    """A collection whose pipeline has no embed node cannot be searched (409)."""
    from backend.context import CONTEXT

    collection = SimpleNamespace(
        pipeline={
            "node_type": "group",
            "id": "root",
            "nodes": [],
            "transitions": [],
            "bindings": {},
        }
    )
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    response = client.post(
        "/api/v1/collections/33333333-3333-3333-3333-333333333333/search",
        json={"query": "q"},
    )
    assert response.status_code == 409, response.text


async def test_query_embedder_probe_blocks_a_disallowed_host(fastapi_app, monkeypatch) -> None:
    """The 424-classifier probe rebuilds an embedder from a caller-influenced base_url, so it must
    honour the egress allowlist too (the health sweep does). With the allowlist set to a host that is
    NOT the embed node's, classify reports BLOCKED and never touches the network — a raising httpx
    client proves no probe happened (a probe would classify UNREACHABLE, not BLOCKED)."""
    import httpx

    from backend.libs.search import QueryEmbedderProbe  # noqa: PLC0415
    from config import RUNTIME_CONFIG  # noqa: PLC0415
    from shared_libs.pipelines.reachability import ProbeStatus  # noqa: PLC0415

    monkeypatch.setattr(RUNTIME_CONFIG, "PROVIDER_EGRESS_ALLOWLIST", "only-other-host")

    class _Boom:
        def __init__(self, *a: object, **k: object) -> None: ...
        async def __aenter__(self) -> "_Boom":
            return self

        async def __aexit__(self, *e: object) -> None: ...
        async def get(self, *a: object, **k: object) -> None:
            raise AssertionError("a blocked host must never be probed")

    monkeypatch.setattr(httpx, "AsyncClient", _Boom)

    status = await QueryEmbedderProbe().classify(_pipeline_with_embed())
    assert status is ProbeStatus.BLOCKED
