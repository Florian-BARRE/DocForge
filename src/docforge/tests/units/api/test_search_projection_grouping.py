"""Search lean responses: the ``return_fields`` hit projection and the ``group_by="document"`` cap.

Covers the wire contract (the default response is unchanged; a projected hit carries ONLY the requested
keys, absent — not null — through FastAPI's response_model serialization; identity keys always kept;
unknown names → 422), the hydration saving (the read port skips the geometry / metadata / document reads
of unrequested fields), and the per-document cap (order kept, filled from other documents, fewer when
impossible, request bounds). ``from backend...`` imports are deferred until after ``fastapi_app``.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.public_models import FieldType
from shared_libs.public_models.search import Hit, SearchResult

_URL = "/api/v1/collections/33333333-3333-3333-3333-333333333333/search"

_FULL_HIT_KEYS = {
    "chunk_id",
    "document_id",
    "filename",
    "document_title",
    "heading_path",
    "metadata",
    "score",
    "text",
    "chunk_index",
    "token_count",
    "block_ids",
    "page",
    "page_number",
    "bbox",
    "block_locations",
}


def _pipeline_with_embed() -> dict:
    """A minimal pipeline blob carrying one embed action node."""
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


def _hit(chunk: int, document: str, score: float) -> Hit:
    """A hydrated graph Hit with geometry + metadata in its bag (as the read port emits)."""
    return Hit(
        chunk_id=f"11111111-1111-1111-1111-{chunk:012d}",
        document_id=document,
        score=score,
        rank=chunk,
        text=f"chunk text {chunk}",
        metadata={
            "chunk_index": chunk,
            "token_count": 40,
            "heading_path": ["Chapter II"],
            "filename": "gdpr.pdf",
            "document_title": "EU Regulation",
            "document_metadata": {"jurisdiction": "EU", "article_ref": "Article 5"},
            "block_ids": ["doc:#/texts/1"],
            "page": 4,
            "bbox": [0.1, 0.2, 0.3, 0.4],
            "block_locations": [{"page": 4, "bbox": [0.1, 0.2, 0.3, 0.4]}],
        },
    )


@pytest.fixture
def wired(fastapi_app, monkeypatch):
    """Patch the collection reads + the search service; return the captured search() mock."""
    from backend.context import CONTEXT  # noqa: PLC0415

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search={})
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    schema = [SimpleNamespace(field_name="topic", filterable=True, field_type=FieldType.STRING)]
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=schema))
    result = SearchResult(query="q", hits=[_hit(1, "doc-a", 0.9), _hit(2, "doc-b", 0.8)])
    search = AsyncMock(return_value=(result, (0, 0, None, 0)))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return search


# ---------------------------------------------------------------- B1 — return_fields projection


def test_default_response_is_the_full_hit(client, wired) -> None:
    """No return_fields → every hit field and every envelope key is present (REST-compatible)."""
    response = client.post(_URL, json={"query": "audit", "limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()

    # 1. The envelope keeps all six keys — even the null/empty ones (exclude_unset never drops them).
    assert set(body) == {"query", "hits", "cost", "score_kind", "debug_info", "hints"}
    assert body["cost"] is None and body["hints"] == []
    # 2. Every hit carries the full field set, geometry included, and the block location shape.
    for hit in body["hits"]:
        assert set(hit) == _FULL_HIT_KEYS
        assert set(hit["block_locations"][0]) == {"page", "page_number", "bbox"}
    assert body["hits"][0]["page_number"] == 5
    # 3. The service hydrates everything and does not group.
    assert wired.await_args.kwargs["projection"] is None
    assert wired.await_args.kwargs["max_per_document"] is None


def test_return_fields_keeps_only_requested_keys_absent_not_null(client, wired) -> None:
    """A projected hit carries ONLY the requested keys + identity; the rest are absent from the JSON."""
    response = client.post(
        _URL, json={"query": "audit", "return_fields": ["text", "score", "page_number"]}
    )
    assert response.status_code == 200, response.text

    for hit in response.json()["hits"]:
        assert set(hit) == {"chunk_id", "document_id", "text", "score", "page_number"}
    assert response.json()["hits"][0]["page_number"] == 5
    # The projection reached the service (so the read port can skip the unrequested reads).
    projection = wired.await_args.kwargs["projection"]
    assert projection.fields == {"chunk_id", "document_id", "text", "score", "page_number"}


def test_return_fields_single_metadata_entry(client, wired) -> None:
    """metadata.<field> keeps a metadata dict holding only that key."""
    response = client.post(
        _URL, json={"query": "audit", "return_fields": ["metadata.jurisdiction", "text"]}
    )
    assert response.status_code == 200, response.text
    hit = response.json()["hits"][0]
    assert set(hit) == {"chunk_id", "document_id", "metadata", "text"}
    assert hit["metadata"] == {"jurisdiction": "EU"}


def test_return_fields_whole_metadata_wins_over_single_keys(client, wired) -> None:
    """Asking for both 'metadata' and 'metadata.x' returns the whole metadata dict."""
    response = client.post(
        _URL, json={"query": "audit", "return_fields": ["metadata", "metadata.jurisdiction"]}
    )
    assert response.json()["hits"][0]["metadata"] == {
        "jurisdiction": "EU",
        "article_ref": "Article 5",
    }


def test_return_fields_empty_list_keeps_identity_only(client, wired) -> None:
    """An empty selection still returns each hit's identity (chunk_id + document_id)."""
    response = client.post(_URL, json={"query": "audit", "return_fields": []})
    assert response.status_code == 200, response.text
    assert all(set(hit) == {"chunk_id", "document_id"} for hit in response.json()["hits"])


@pytest.mark.parametrize("bad", ["txt", "metadata.", "rank"])
def test_return_fields_unknown_name_is_422_listing_allowed(client, wired, bad) -> None:
    """An unknown field name is rejected before any spend, naming the allowed names."""
    response = client.post(_URL, json={"query": "audit", "return_fields": ["text", bad]})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert bad in detail and "page_number" in detail and "metadata.<field>" in detail
    wired.assert_not_awaited()


def test_openapi_hit_schema_requires_only_identity(fastapi_app) -> None:
    """The response schema is honest: a projected hit may omit every field but its identity."""
    schemas = fastapi_app.openapi()["components"]["schemas"]
    assert sorted(schemas["SearchHitModel"]["required"]) == ["chunk_id", "document_id"]
    request = schemas["SearchRequest"]["properties"]
    assert {"return_fields", "group_by", "max_per_document"} <= set(request)


# ---------------------------------------------------------------- B1 — skip the hydration work


def _port_database(doc_uuid: uuid.UUID, chunk_uuid: uuid.UUID) -> SimpleNamespace:
    """A documents facade double whose reads are all AsyncMocks (asserted awaited or not)."""
    row = SimpleNamespace(
        id=chunk_uuid,
        document_id=doc_uuid,
        text="Audit rights.",
        chunk_index=7,
        token_count=12,
        heading_path=[],
    )
    return SimpleNamespace(
        documents=SimpleNamespace(
            get_chunks_by_ids=AsyncMock(return_value=[row]),
            get_by_ids=AsyncMock(
                return_value=[SimpleNamespace(id=doc_uuid, filename="c.pdf", title="C")]
            ),
            get_filterable_metadata_for_documents=AsyncMock(return_value={doc_uuid: {"k": "v"}}),
            get_block_locations_for_chunks=AsyncMock(
                return_value={
                    str(chunk_uuid): [{"block_id": "b1", "page": 2, "bbox": [0, 0, 1, 1]}]
                }
            ),
        )
    )


def test_read_port_skips_unrequested_hydration_reads(fastapi_app) -> None:
    """A text/score-only projection never runs the geometry, metadata or document reads."""
    from backend.libs.search import CollectionReadPortImpl, HitProjection  # noqa: PLC0415

    doc_uuid, chunk_uuid = uuid.uuid4(), uuid.uuid4()
    database = _port_database(doc_uuid, chunk_uuid)
    projection, _ = HitProjection.from_request(["text", "score"], ["text", "score"])
    port = CollectionReadPortImpl(database, uuid.uuid4(), projection=projection)

    hit = asyncio.run(port.hydrate([str(chunk_uuid)]))[str(chunk_uuid)]

    assert hit.text == "Audit rights."
    database.documents.get_block_locations_for_chunks.assert_not_awaited()
    database.documents.get_filterable_metadata_for_documents.assert_not_awaited()
    database.documents.get_by_ids.assert_not_awaited()


def test_read_port_reads_geometry_only_when_a_geometry_field_is_requested(fastapi_app) -> None:
    """page_number is geometry-derived: requesting it runs the block-location read (only that)."""
    from backend.libs.search import CollectionReadPortImpl, HitProjection  # noqa: PLC0415

    doc_uuid, chunk_uuid = uuid.uuid4(), uuid.uuid4()
    database = _port_database(doc_uuid, chunk_uuid)
    projection, _ = HitProjection.from_request(["page_number"], ["page_number"])
    port = CollectionReadPortImpl(database, uuid.uuid4(), projection=projection)

    hit = asyncio.run(port.hydrate([str(chunk_uuid)]))[str(chunk_uuid)]

    assert hit.metadata["page"] == 2
    database.documents.get_block_locations_for_chunks.assert_awaited_once()
    database.documents.get_filterable_metadata_for_documents.assert_not_awaited()


def test_read_port_without_projection_reads_everything(fastapi_app) -> None:
    """No projection (the default) keeps every hydration read — the full hit, unchanged."""
    from backend.libs.search import CollectionReadPortImpl  # noqa: PLC0415

    doc_uuid, chunk_uuid = uuid.uuid4(), uuid.uuid4()
    database = _port_database(doc_uuid, chunk_uuid)
    hit = asyncio.run(CollectionReadPortImpl(database, uuid.uuid4()).hydrate([str(chunk_uuid)]))[
        str(chunk_uuid)
    ]

    assert hit.metadata["document_metadata"] == {"k": "v"}
    assert hit.metadata["filename"] == "c.pdf"
    database.documents.get_block_locations_for_chunks.assert_awaited_once()


# ---------------------------------------------------------------- B2 — group by document


def test_group_by_threads_the_cap_to_the_service(client, wired) -> None:
    """group_by='document' passes max_per_document (default 1) to the service."""
    client.post(_URL, json={"query": "audit", "group_by": "document"})
    assert wired.await_args.kwargs["max_per_document"] == 1
    client.post(_URL, json={"query": "audit", "group_by": "document", "max_per_document": 3})
    assert wired.await_args.kwargs["max_per_document"] == 3


@pytest.mark.parametrize(
    "body",
    [
        {"max_per_document": 2},
        {"group_by": "document", "max_per_document": 0},
        {"group_by": "document", "max_per_document": 11},
        {"group_by": "chunk"},
    ],
)
def test_group_by_request_bounds_are_422(client, wired, body) -> None:
    """Out-of-bounds caps, an unknown grouping and an orphan max_per_document are rejected."""
    response = client.post(_URL, json={"query": "audit", **body})
    assert response.status_code == 422, response.text
    wired.assert_not_awaited()


def _ranked(*documents: str) -> list[Hit]:
    """Hits ranked best-first, one per given document id (repeat an id for same-doc hits)."""
    return [
        Hit(chunk_id=f"c{i}", document_id=doc, score=1.0 - i / 100, rank=i)
        for i, doc in enumerate(documents, start=1)
    ]


def test_cap_keeps_order_and_fills_from_other_documents(fastapi_app) -> None:
    """At most N per document, ranking order kept, the page filled with other documents' hits."""
    from backend.libs.search import DocumentHitGrouper  # noqa: PLC0415

    hits = _ranked("a", "a", "b", "a", "c", "b", "d")

    capped = DocumentHitGrouper.cap(hits, limit=3, max_per_document=1)
    assert [hit.chunk_id for hit in capped] == ["c1", "c3", "c5"]
    assert [hit.rank for hit in capped] == [1, 2, 3]

    capped = DocumentHitGrouper.cap(hits, limit=5, max_per_document=2)
    assert [hit.chunk_id for hit in capped] == ["c1", "c2", "c3", "c5", "c6"]


def test_cap_returns_fewer_when_too_few_documents(fastapi_app) -> None:
    """Never duplicates beyond the cap — returns fewer hits than the limit instead."""
    from backend.libs.search import DocumentHitGrouper  # noqa: PLC0415

    capped = DocumentHitGrouper.cap(_ranked("a", "a", "b", "b"), limit=10, max_per_document=1)
    assert [hit.document_id for hit in capped] == ["a", "b"]


def test_fetch_depth_over_fetches_within_bounds(fastapi_app) -> None:
    """The graph page grows with the cap's pruning power, bounded by MAX_FETCH_DEPTH."""
    from backend.libs.search import DocumentHitGrouper  # noqa: PLC0415
    from backend.libs.search.document_grouping import MAX_FETCH_DEPTH  # noqa: PLC0415

    assert DocumentHitGrouper.fetch_depth(10, 1) == 30
    assert DocumentHitGrouper.fetch_depth(10, 5) == 100
    assert DocumentHitGrouper.fetch_depth(100, 10) == MAX_FETCH_DEPTH
    assert DocumentHitGrouper.fetch_depth(1, 1) == 3


def test_service_over_fetches_then_caps_the_final_ranking(fastapi_app, monkeypatch) -> None:
    """SearchService asks the graph for the deeper page, then caps its output per document."""
    from backend.libs.search import service as service_module  # noqa: PLC0415

    monkeypatch.setattr(
        service_module.SearchContractBuilder, "build", staticmethod(lambda _c: SimpleNamespace())
    )
    service = service_module.SearchService(database=SimpleNamespace())
    graph_result = SearchResult(query="q", hits=_ranked("a", "a", "b", "c"), debug={"hit_count": 4})

    async def _fake_run(*args, finalize=None, **kwargs):
        # The real runner applies `finalize` before emitting its metrics — mirror that here.
        answer = finalize(graph_result) if finalize is not None else graph_result
        return answer, (0, 0, None, 0)

    run = AsyncMock(side_effect=_fake_run)
    monkeypatch.setattr(service._runner, "run", run)
    collection = SimpleNamespace(search={}, estimate_overrides=None)

    result, _ = asyncio.run(
        service.search(uuid.uuid4(), "q", top_k=2, collection=collection, max_per_document=1)
    )

    # 1. The graph was asked for the over-fetched page (2 * 3), not the caller's limit.
    assert run.await_args.args[1]["query"].top_k == 6
    # 2. The delivered hits are capped per document, in ranking order, and the debug bag says so.
    assert [hit.chunk_id for hit in result.hits] == ["c1", "c3"]
    assert result.debug == {
        "hit_count": 2,
        "grouping": {"by": "document", "max_per_document": 1, "fetched": 4},
    }

    # 3. The cap runs INSIDE the runner (via finalize) so its metrics count delivered hits.
    assert run.await_args.kwargs["finalize"] is not None

    # 4. Without grouping the caller's limit is passed through and nothing is capped.
    asyncio.run(service.search(uuid.uuid4(), "q", top_k=2, collection=collection))
    assert run.await_args.args[1]["query"].top_k == 2
    assert run.await_args.kwargs["finalize"] is None


def test_runner_applies_finalize_before_metrics(fastapi_app, monkeypatch) -> None:
    """The per-search metrics see the FINALIZED (capped) answer, not the over-fetched page."""
    from backend.libs.search import runner as runner_module  # noqa: PLC0415

    seen: list[int] = []
    monkeypatch.setattr(
        runner_module.SearchMetricsEmitter,
        "emit",
        staticmethod(lambda **kwargs: seen.append(len(kwargs["result"].hits))),
    )
    monkeypatch.setattr(
        runner_module.SearchMetricsEmitter, "family_map", staticmethod(lambda group: {})
    )
    monkeypatch.setattr(
        runner_module.UsageSummer, "summarize", staticmethod(lambda record, rates: (0, 0, None, 0))
    )
    graph_result = SearchResult(query="q", hits=_ranked("a", "a", "b", "c"), debug={"hit_count": 4})
    runner = runner_module.SearchRunner()
    group = SimpleNamespace(id="g", children=[])
    monkeypatch.setattr(runner._pool, "acquire", lambda key, build: group)
    monkeypatch.setattr(runner._pool, "release", lambda key, grp: None)

    async def _execute(*args, **kwargs):
        return SimpleNamespace(result=graph_result), SimpleNamespace(children=[], error=None)

    monkeypatch.setattr(runner, "_engine", SimpleNamespace(execute=_execute))

    result, _ = asyncio.run(
        runner.run(
            {},
            {},
            SimpleNamespace(),
            None,
            graph_key="k",
            finalize=lambda answer: answer.model_copy(update={"hits": answer.hits[:1]}),
        )
    )

    assert len(result.hits) == 1
    assert seen == [1]  # metrics recorded the delivered count, not the 4-hit page
