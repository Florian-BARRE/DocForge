"""Search route — per-request tuning (C3) and the blank-query browse pointer.

The service is mocked; these pin the wire contract: the knobs reach the service as a SearchTuning, the
default response is unchanged (no debug keys), debug adds fusion_score/rerank_score per hit (also on
top of a projection), a SearchTuningError is a 422, score_kind follows a skipped rerank / fusion
override, and a blank or missing query 422s pointing at the browse endpoint.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shared_libs.pipelines.search import SearchPipeline
from shared_libs.public_models import FieldType
from shared_libs.public_models.search import Hit, SearchResult

_URL = "/api/v1/collections/33333333-3333-3333-3333-333333333333/search"


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


def _wire(monkeypatch, search_blob: dict, hits: list[Hit]) -> AsyncMock:
    """Patch the collection reads + the search service; return the search() mock."""
    from backend.context import CONTEXT  # noqa: PLC0415

    collection = SimpleNamespace(pipeline=_pipeline_with_embed(), search=search_blob)
    monkeypatch.setattr(CONTEXT.database.collections, "get", AsyncMock(return_value=collection))
    schema = [SimpleNamespace(field_name="topic", filterable=True, field_type=FieldType.STRING)]
    monkeypatch.setattr(CONTEXT.database.collections, "get_schema", AsyncMock(return_value=schema))
    search = AsyncMock(return_value=(SearchResult(query="q", hits=hits), (0, 0, None, 0)))
    monkeypatch.setattr(CONTEXT.search_service, "search", search)
    return search


_RERANKED = Hit(
    chunk_id="11111111-1111-1111-1111-000000000001",
    document_id="doc-a",
    score=0.91,
    text="t",
    metadata={"chunk_index": 1},
    fusion_score=0.03,
    rerank_score=0.91,
)
_FUSED = Hit(
    chunk_id="11111111-1111-1111-1111-000000000002",
    document_id="doc-b",
    score=0.02,
    text="u",
    metadata={"chunk_index": 2},
    fusion_score=0.02,
)


def test_default_request_passes_an_untuned_search_and_no_debug_keys(client, monkeypatch) -> None:
    """No tuning knob → an all-default SearchTuning; hits carry no fusion/rerank keys."""
    from backend.libs.search import SearchTuning  # noqa: PLC0415

    search = _wire(monkeypatch, {}, [_RERANKED])
    body = client.post(_URL, json={"query": "audit"}).json()

    assert search.await_args.kwargs["tuning"] == SearchTuning()
    assert "fusion_score" not in body["hits"][0] and "rerank_score" not in body["hits"][0]
    assert body["score_kind"] == "rrf_fusion"


def test_knobs_reach_the_service(client, monkeypatch) -> None:
    """min_score / rerank / fusion / debug arrive verbatim on the SearchTuning."""
    from backend.libs.search import SearchTuning  # noqa: PLC0415

    search = _wire(monkeypatch, {}, [])
    payload = {"query": "q", "min_score": 0.3, "rerank": False, "fusion": "dbsf", "debug": True}
    response = client.post(_URL, json=payload)

    assert response.status_code == 200, response.text
    assert search.await_args.kwargs["tuning"] == SearchTuning(
        min_score=0.3, rerank=False, fusion="dbsf", debug=True
    )
    assert response.json()["score_kind"] == "dbsf_fusion"


def test_debug_adds_fusion_and_rerank_scores(client, monkeypatch) -> None:
    """debug=true → fusion_score on every hit, rerank_score only on a reranked one."""
    _wire(monkeypatch, {}, [_RERANKED, _FUSED])
    hits = client.post(_URL, json={"query": "q", "debug": True}).json()["hits"]

    assert (hits[0]["fusion_score"], hits[0]["rerank_score"]) == (0.03, 0.91)
    assert hits[1]["fusion_score"] == 0.02 and "rerank_score" not in hits[1]


def test_debug_composes_with_a_projection(client, monkeypatch) -> None:
    """The debug scores ride on top of return_fields without re-adding unrequested keys."""
    _wire(monkeypatch, {}, [_RERANKED])
    hit = client.post(_URL, json={"query": "q", "debug": True, "return_fields": ["score"]}).json()[
        "hits"
    ][0]
    assert set(hit) == {"chunk_id", "document_id", "score", "fusion_score", "rerank_score"}


def test_debug_fields_are_not_projectable(client, monkeypatch) -> None:
    """fusion_score is switched on by debug, never named in return_fields (422)."""
    _wire(monkeypatch, {}, [])
    response = client.post(_URL, json={"query": "q", "return_fields": ["fusion_score"]})
    assert response.status_code == 422
    assert "fusion_score" in response.text


def test_rerank_false_on_a_rerank_blob_reports_the_fusion_kind(client, monkeypatch) -> None:
    """A skipped rerank delivers fusion scores, so score_kind is the fusion kind."""
    rerank_blob = SearchPipeline.rerank_blob().model_dump(mode="json")
    _wire(monkeypatch, rerank_blob, [])
    assert client.post(_URL, json={"query": "q"}).json()["score_kind"] == "cross_encoder_rerank"
    body = client.post(_URL, json={"query": "q", "rerank": False}).json()
    assert body["score_kind"] == "rrf_fusion"


def test_tuning_error_is_a_422(client, monkeypatch) -> None:
    """rerank=true on a graph without a rerank stage → 422 with the service's message."""
    from backend.libs.search import SearchTuningError  # noqa: PLC0415

    search = _wire(monkeypatch, {}, [])
    search.side_effect = SearchTuningError(
        "rerank=true but this collection's search pipeline has no rerank stage"
    )
    response = client.post(_URL, json={"query": "q", "rerank": True})
    assert response.status_code == 422
    assert "no rerank stage" in response.json()["detail"]


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "   "}, {"filters": {"topic": "x"}}])
def test_blank_or_missing_query_points_to_browse(client, monkeypatch, payload) -> None:
    """A blank/missing query keeps its 422, now naming the browse endpoint."""
    _wire(monkeypatch, {}, [])
    response = client.post(_URL, json=payload)
    assert response.status_code == 422
    assert "use POST /collections/{id}/chunks/browse to list chunks by filter" in response.text


def test_min_score_must_be_non_negative(client, monkeypatch) -> None:
    """A negative threshold is rejected by the request model."""
    _wire(monkeypatch, {}, [])
    assert client.post(_URL, json={"query": "q", "min_score": -0.1}).status_code == 422


# ---------------------------------------------------------------- SearchService wiring


def _service_with_captured_run(monkeypatch):
    """A SearchService whose runner records (blob, run_input, finalize) instead of running."""
    from backend.libs.search import service as service_module  # noqa: PLC0415

    captured: dict = {}

    async def _run(self, blob, run_input, read_port, rates, graph_key, timeout_seconds, finalize):
        captured.update(blob=blob, run_input=run_input, finalize=finalize)
        return SearchResult(query="q"), (0, 0, None, 0)

    monkeypatch.setattr(service_module.SearchRunner, "run", _run)
    monkeypatch.setattr(service_module.SearchContractBuilder, "build", lambda collection: None)
    return service_module.SearchService(database=SimpleNamespace()), captured


async def test_service_turns_tuning_into_query_flags(fastapi_app, monkeypatch) -> None:
    """rerank=False / fusion ride as QuerySpec flags; min_score yields a finalize step."""
    from backend.libs.search import SearchTuning  # noqa: PLC0415
    from shared_libs.public_models.search import FUSION_FLAG, RERANK_FLAG  # noqa: PLC0415

    service, captured = _service_with_captured_run(monkeypatch)
    collection = SimpleNamespace(search={}, estimate_overrides=None)
    await service.search("cid", "q", collection=collection)
    assert captured["run_input"]["query"].flags == {}
    assert captured["finalize"] is None

    tuning = SearchTuning(rerank=False, fusion="dbsf", min_score=0.2)
    await service.search("cid", "q", collection=collection, tuning=tuning)
    assert captured["run_input"]["query"].flags == {RERANK_FLAG: False, FUSION_FLAG: "dbsf"}
    assert captured["finalize"] is not None


async def test_service_rejects_rerank_true_without_a_rerank_stage(fastapi_app, monkeypatch) -> None:
    """rerank=True on the stock (rerank-less) graph raises before the run; a rerank blob runs."""
    from backend.libs.search import SearchTuning, SearchTuningError  # noqa: PLC0415

    service, captured = _service_with_captured_run(monkeypatch)
    with pytest.raises(SearchTuningError):
        await service.search(
            "cid",
            "q",
            collection=SimpleNamespace(search={}, estimate_overrides=None),
            tuning=SearchTuning(rerank=True),
        )
    assert "blob" not in captured

    rerank_blob = SearchPipeline.rerank_blob().model_dump(mode="json")
    await service.search(
        "cid",
        "q",
        collection=SimpleNamespace(search=rerank_blob, estimate_overrides=None),
        tuning=SearchTuning(rerank=True),
    )
    assert captured["blob"]["nodes"]


def test_min_score_emptying_the_answer_is_explained_not_blamed_on_filters(
    client, monkeypatch
) -> None:
    """Every hit cut by min_score → a min_score hint (with the best score), never a filter culprit."""
    search = _wire(monkeypatch, {}, [])
    cut = SearchResult(
        query="q",
        hits=[],
        debug={
            "hit_count": 0,
            "min_score": {"threshold": 0.5, "dropped": 2, "top_dropped_score": 0.031},
        },
    )
    search.return_value = (cut, (0, 0, None, 0))

    response = client.post(_URL, json={"query": "q", "min_score": 0.5})

    assert response.status_code == 200, response.text
    hints = response.json()["hints"]
    assert [hint["field"] for hint in hints] == ["min_score"]
    assert "2 hit(s)" in hints[0]["message"]


def _wire_single_branch(monkeypatch, search_blob: dict, axes: str, fused: bool) -> None:
    """Patch the service so the run's read port records ONE retrieval call on the router's probe."""
    search = _wire(monkeypatch, search_blob, [])
    result = search.return_value

    async def _run(*_args, **kwargs):
        kwargs["probe"].record_call(axes, False, [], fused=fused)
        return result

    search.side_effect = _run


@pytest.mark.parametrize(
    ("axes", "expected"), [("dense_only", "raw_dense"), ("sparse_only", "raw_sparse")]
)
def test_single_vector_search_reports_the_raw_score_kind(client, monkeypatch, axes, expected):
    """One vector queried directly (no fusion ran) → score_kind names the raw scale, even under a
    fusion override (there was nothing to fuse)."""
    _wire_single_branch(monkeypatch, {}, axes, fused=False)
    assert client.post(_URL, json={"query": "q"}).json()["score_kind"] == expected
    assert client.post(_URL, json={"query": "q", "fusion": "dbsf"}).json()["score_kind"] == expected


def test_fused_search_keeps_the_fusion_kind(client, monkeypatch) -> None:
    """Several branches fused → the fusion label stays (dense_only axis with 2 dense vectors)."""
    _wire_single_branch(monkeypatch, {}, "dense_only", fused=True)
    assert client.post(_URL, json={"query": "q"}).json()["score_kind"] == "rrf_fusion"


def test_rerank_wins_over_a_raw_retrieval(client, monkeypatch) -> None:
    """A reranker that scored the hits labels them, whatever the retrieval's raw scale was."""
    rerank_blob = SearchPipeline.rerank_blob().model_dump(mode="json")
    _wire_single_branch(monkeypatch, rerank_blob, "dense_only", fused=False)
    assert client.post(_URL, json={"query": "q"}).json()["score_kind"] == "cross_encoder_rerank"
    body = client.post(_URL, json={"query": "q", "rerank": False}).json()
    assert body["score_kind"] == "raw_dense"
