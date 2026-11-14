# ====== Code Summary ======
# Characterization (safety net) of the bge_server inference routes — /embed, /embed_sparse, /embed_all,
# /embed_colbert, /rerank — on the full create_app() (gzip middleware included, lifespan NOT run, no
# model loaded): the batching engine and the model service are fakes with canned answers. The raw
# response text (status + body, so separators and float formatting count) of each happy-path request is
# pinned to goldens/inference_routes.json; the error contract (422 size ceilings, 503 back-pressure and
# reranker gate, 500) and the engine call arguments are asserted explicitly. It records TODAY's
# behaviour on main so the bge split (R-28) cannot change it: a failing test is a refactor decision.
#
# To regenerate the golden after a REVIEWED, intended change (from src/bge_server):
#   uv run --no-sync python -c "import json; \
#     from tests.characterization.test_inference_routes_golden import record_all; \
#     print(json.dumps(record_all(), indent=2, sort_keys=True, ensure_ascii=False))" \
#     > tests/characterization/goldens/inference_routes.json

# ====== Standard Library Imports ======
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.app import create_app
from backend.context import CONTEXT
from config_loader import BgeServerConfig
from libs.batching import QueueFullError

GOLDEN_PATH = Path(__file__).parent / "goldens" / "inference_routes.json"

# Engine answers use int where the response model says float (and numeric strings never): the routes
# coerce them, which the raw-text golden captures (`1` in the engine -> `1.0` on the wire).
DENSE = [[1.0, 2.0], [3.0, 4.0]]
SPARSE_RAW = [[{"index": 5, "value": 1}], [{"index": 7, "value": 0.8}, {"index": 9, "value": 0.25}]]
COLBERT = [[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.6]]]
RERANK_RAW = [{"index": 1, "score": 0.2}, {"index": 0, "score": 1}]

# name -> (path, JSON body): every happy-path request recorded in the golden.
CASES: dict[str, tuple[str, dict[str, Any]]] = {
    "embed_list": ("/embed", {"inputs": ["t1", "t2"]}),
    "embed_single_string": ("/embed", {"inputs": "t1"}),
    "embed_empty": ("/embed", {"inputs": []}),
    "embed_sparse_list": ("/embed_sparse", {"inputs": ["t1", "t2"]}),
    "embed_sparse_empty": ("/embed_sparse", {"inputs": []}),
    "embed_all_list": ("/embed_all", {"inputs": ["t1", "t2"]}),
    "embed_all_empty": ("/embed_all", {"inputs": []}),
    "embed_colbert_list": ("/embed_colbert", {"inputs": ["t1", "t2"]}),
    "embed_colbert_empty": ("/embed_colbert", {"inputs": []}),
    "rerank_two_candidates": ("/rerank", {"query": "q", "texts": ["a", "b"]}),
    "rerank_no_candidates": ("/rerank", {"query": "q", "texts": []}),
}


def _build_engine() -> MagicMock:
    """A fake batching engine answering every queued route with the canned shapes above."""
    engine = MagicMock()
    engine.submit_embed_dense = AsyncMock(return_value=DENSE)
    engine.submit_embed_sparse = AsyncMock(return_value=SPARSE_RAW)
    engine.submit_embed_colbert = AsyncMock(return_value=COLBERT)
    engine.embed_all = AsyncMock(return_value=(DENSE, SPARSE_RAW))
    engine.submit_rerank = AsyncMock(return_value=RERANK_RAW)
    return engine


def _wire_context() -> MagicMock:
    """Point CONTEXT at the real config, a fake engine and a fake model service; return the engine."""
    engine = _build_engine()
    models = MagicMock()
    models.reranker_loaded = True
    CONTEXT.CONFIG = BgeServerConfig
    CONTEXT.batching_engine = engine
    CONTEXT.bge_models = models
    return engine


def record_all() -> dict[str, dict[str, Any]]:
    """Run every golden case against a fresh app and return {case: {status, body}} (raw text)."""
    _wire_context()
    client = TestClient(create_app())
    recorded: dict[str, dict[str, Any]] = {}
    for name, (path, body) in CASES.items():
        response = client.post(path, json=body)
        recorded[name] = {"status": response.status_code, "body": response.text}
    return recorded


@pytest.fixture
def engine() -> MagicMock:
    return _wire_context()


@pytest.fixture
def client(engine: MagicMock) -> TestClient:
    return TestClient(create_app())


# ── Golden: the happy-path wire format ───────────────────────────────────────


@pytest.mark.parametrize("case", sorted(CASES))
def test_happy_path_response_matches_the_golden(client: TestClient, case: str) -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    path, body = CASES[case]

    response = client.post(path, json=body)

    assert {"status": response.status_code, "body": response.text} == golden[case]


def test_golden_covers_exactly_the_declared_cases() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert sorted(golden) == sorted(CASES)


# ── Content types ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/embed", "/embed_sparse", "/embed_all", "/embed_colbert"])
def test_embedding_routes_answer_application_json(client: TestClient, path: str) -> None:
    response = client.post(path, json={"inputs": ["t1"]})

    assert response.headers["content-type"].startswith("application/json")


# ── What each route asks of the engine ───────────────────────────────────────


def test_single_string_input_reaches_the_engine_as_a_one_item_list(
    client: TestClient, engine: MagicMock
) -> None:
    client.post("/embed", json={"inputs": "only"})

    engine.submit_embed_dense.assert_awaited_once_with(["only"])


def test_each_embedding_route_calls_its_own_engine_queue(
    client: TestClient, engine: MagicMock
) -> None:
    client.post("/embed_sparse", json={"inputs": ["a"]})
    client.post("/embed_colbert", json={"inputs": ["b"]})
    client.post("/embed_all", json={"inputs": ["c"]})

    engine.submit_embed_sparse.assert_awaited_once_with(["a"])
    engine.submit_embed_colbert.assert_awaited_once_with(["b"])
    engine.embed_all.assert_awaited_once_with(["c"])
    engine.submit_embed_dense.assert_not_awaited()


def test_rerank_forwards_query_and_candidates_and_keeps_the_engine_order(
    client: TestClient, engine: MagicMock
) -> None:
    response = client.post("/rerank", json={"query": "q", "texts": ["a", "b"]})

    engine.submit_rerank.assert_awaited_once_with("q", ["a", "b"])
    assert [item["index"] for item in response.json()] == [1, 0]


def test_empty_requests_never_reach_the_engine(client: TestClient, engine: MagicMock) -> None:
    for name in ("embed_empty", "embed_sparse_empty", "embed_all_empty", "embed_colbert_empty"):
        path, body = CASES[name]
        client.post(path, json=body)
    client.post("/rerank", json=CASES["rerank_no_candidates"][1])

    engine.submit_embed_dense.assert_not_awaited()
    engine.submit_embed_sparse.assert_not_awaited()
    engine.submit_embed_colbert.assert_not_awaited()
    engine.embed_all.assert_not_awaited()
    engine.submit_rerank.assert_not_awaited()


# ── Request validation (422) ─────────────────────────────────────────────────


def test_missing_inputs_field_is_422(client: TestClient) -> None:
    response = client.post("/embed", json={})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "inputs"]


def test_more_items_than_the_request_ceiling_is_422_before_the_engine(
    client: TestClient, engine: MagicMock
) -> None:
    items = ["x"] * (BgeServerConfig.BGE_MAX_REQUEST_ITEMS + 1)

    response = client.post("/embed", json={"inputs": items})

    assert response.status_code == 422
    assert "request ceiling" in response.json()["detail"][0]["msg"]
    engine.submit_embed_dense.assert_not_awaited()


def test_a_text_over_the_per_item_char_ceiling_is_422(client: TestClient) -> None:
    text = "x" * (BgeServerConfig.BGE_MAX_TEXT_CHARS + 1)

    response = client.post("/embed_sparse", json={"inputs": [text]})

    assert response.status_code == 422
    assert "per-item ceiling" in response.json()["detail"][0]["msg"]


def test_rerank_candidate_over_the_char_ceiling_is_422(client: TestClient) -> None:
    text = "x" * (BgeServerConfig.BGE_MAX_TEXT_CHARS + 1)

    response = client.post("/rerank", json={"query": "q", "texts": [text]})

    assert response.status_code == 422


def test_rerank_more_candidates_than_the_item_ceiling_is_422(client: TestClient) -> None:
    texts = ["x"] * (BgeServerConfig.BGE_MAX_REQUEST_ITEMS + 1)

    response = client.post("/rerank", json={"query": "q", "texts": texts})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "texts"]


# ── Back-pressure, reranker gate and server faults ───────────────────────────


@pytest.mark.parametrize(
    ("path", "body", "method_name"),
    [
        ("/embed", {"inputs": ["t"]}, "submit_embed_dense"),
        ("/embed_sparse", {"inputs": ["t"]}, "submit_embed_sparse"),
        ("/embed_colbert", {"inputs": ["t"]}, "submit_embed_colbert"),
        ("/embed_all", {"inputs": ["t"]}, "embed_all"),
        ("/rerank", {"query": "q", "texts": ["t"]}, "submit_rerank"),
    ],
)
def test_queue_full_is_503_with_retry_after_on_every_queued_route(
    client: TestClient,
    engine: MagicMock,
    path: str,
    body: dict[str, Any],
    method_name: str,
) -> None:
    setattr(engine, method_name, AsyncMock(side_effect=QueueFullError("overloaded")))

    response = client.post(path, json=body)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(BgeServerConfig.BGE_RETRY_AFTER_SECONDS)
    assert response.json() == {"detail": {"error": "server overloaded — try again shortly"}}


def test_reranker_not_loaded_is_503_without_retry_after(
    client: TestClient, engine: MagicMock
) -> None:
    cast(MagicMock, CONTEXT.bge_models).reranker_loaded = False

    response = client.post("/rerank", json={"query": "q", "texts": ["a"]})

    assert response.status_code == 503
    assert response.json() == {"detail": {"error": "reranker not loaded (BGE_LOAD_RERANKER=false)"}}
    assert "Retry-After" not in response.headers


def test_engine_failure_is_a_500_carrying_the_error_text(
    client: TestClient, engine: MagicMock
) -> None:
    engine.submit_embed_dense = AsyncMock(side_effect=RuntimeError("model exploded"))

    response = client.post("/embed", json={"inputs": ["t"]})

    assert response.status_code == 500
    assert response.json() == {"detail": {"error": "model exploded"}}


# ── Transport ────────────────────────────────────────────────────────────────


def test_large_embedding_response_is_gzip_compressed(client: TestClient, engine: MagicMock) -> None:
    engine.submit_embed_dense = AsyncMock(return_value=[[0.123456789] * 1024] * 4)

    response = client.post("/embed", json={"inputs": ["t"]}, headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"


def test_embed_routes_only_accept_post(client: TestClient) -> None:
    statuses: Iterator[int] = (client.get(path).status_code for path in ("/embed", "/rerank"))

    assert list(statuses) == [405, 405]
