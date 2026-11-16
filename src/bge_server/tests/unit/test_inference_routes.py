# ====== Code Summary ======
# Route-level tests for the inference router, focused on POST /embed_all. A bare FastAPI app mounts
# only the inference routes (no lifespan, no model load); the runtime's engine is replaced with a
# mock whose async methods return canned shapes. Asserts that /embed_all's `dense` sub-shape matches
# what /embed returns and its `sparse` sub-shape matches what /embed_sparse returns for the same
# input — the like-for-like contract the DocForge app relies on when it falls back to the two routes.
#
# Also covers /embed and /embed_all directly: both now return an explicit ORJSONResponse to skip
# Pydantic response re-validation (see router.py) — these tests pin the exact JSON float shape and
# values a TestClient caller still gets, so that optimization can never silently change the wire
# format.

# ====== Standard Library Imports ======
from typing import cast
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend import BgeServer
from backend.routers import InferenceRoutes
from config_loader import BgeServerConfig
from libs.batching import QueueFullError
from tests.support.bge_app import build_server

# ── Fixtures ──────────────────────────────────────────────────────────────────

_DENSE = [[1.0, 2.0], [3.0, 4.0]]
_SPARSE_RAW = [[{"index": 5, "value": 0.5}], [{"index": 7, "value": 0.8}]]


@pytest.fixture
def server() -> BgeServer:
    """
    Build a BgeServer whose engine is a mock and whose model service is a stub.

    The engine's submit_embed_dense / submit_embed_sparse / embed_all return canned shapes, so no
    model is loaded. The real config class drives request-size validation and max_length
    resolution. The models stub only exposes `reranker_loaded`, which the /rerank route's gate
    reads; it defaults to True (reranker loaded) so /rerank behaves normally unless a test flips it
    to simulate BGE_LOAD_RERANKER=false.

    Returns:
        BgeServer: The server, not yet turned into an app.
    """
    engine = MagicMock()
    engine.submit_embed_dense = AsyncMock(return_value=_DENSE)
    engine.submit_embed_sparse = AsyncMock(return_value=_SPARSE_RAW)
    engine.embed_all = AsyncMock(return_value=(_DENSE, _SPARSE_RAW))
    engine.submit_rerank = AsyncMock(return_value=[{"index": 0, "score": 0.9}])

    models = MagicMock()
    models.reranker_loaded = True
    return build_server(engine=engine, models=models)


@pytest.fixture
def client(server: BgeServer) -> TestClient:
    """A TestClient over a bare app mounting only the inference routes (no lifespan)."""
    app = FastAPI()
    app.include_router(InferenceRoutes(BgeServerConfig, server.runtime).router)
    return TestClient(app)


# ── Test: /embed_all returns {dense, sparse} matching the two separate routes ──


def test_embed_all_shape_matches_separate_routes(client: TestClient, server: BgeServer) -> None:
    """
    POST /embed_all returns {dense, sparse} whose sub-shapes are byte-identical to POST /embed and
    POST /embed_sparse for the same inputs.
    """
    body = {"inputs": ["t1", "t2"]}

    dense_resp = client.post("/embed", json=body)
    sparse_resp = client.post("/embed_sparse", json=body)
    all_resp = client.post("/embed_all", json=body)

    assert dense_resp.status_code == 200
    assert sparse_resp.status_code == 200
    assert all_resp.status_code == 200

    combined = all_resp.json()
    assert combined["dense"] == dense_resp.json()
    assert combined["sparse"] == sparse_resp.json()

    # embed_all no longer takes a per-call max_length — the engine resolves it internally from
    # its own configured max_length (same value the dense/sparse workers use)
    cast(AsyncMock, server.runtime.engine.embed_all).assert_awaited_once_with(["t1", "t2"])


# ── Test: empty input short-circuits without touching the engine ──────────────


def test_embed_all_empty_input(client: TestClient, server: BgeServer) -> None:
    """POST /embed_all with an empty list returns empty sub-lists and never calls the engine."""
    resp = client.post("/embed_all", json={"inputs": []})

    assert resp.status_code == 200
    assert resp.json() == {"dense": [], "sparse": []}
    cast(AsyncMock, server.runtime.engine.embed_all).assert_not_awaited()


# ── Test: /embed_all back-pressure maps QueueFullError to HTTP 503 ────────────


def test_embed_all_queue_full_returns_503(client: TestClient, server: BgeServer) -> None:
    """
    POST /embed_all translates the engine's QueueFullError (in-flight admission cap) into
    HTTP 503 + Retry-After, exactly like the four queued routes.
    """
    cast(MagicMock, server.runtime.engine).embed_all = AsyncMock(
        side_effect=QueueFullError("overloaded")
    )

    resp = client.post("/embed_all", json={"inputs": ["t1"]})

    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == str(BgeServerConfig.BGE_RETRY_AFTER_SECONDS)


# ── Test: /embed returns the exact float matrix via ORJSONResponse ────────────


def test_embed_returns_exact_dense_matrix(client: TestClient) -> None:
    """
    POST /embed still returns the exact float matrix (values unchanged, valid JSON,
    application/json) now that it's built via an explicit ORJSONResponse instead of the
    Pydantic-validated ``list[list[float]]`` response_model path.
    """
    resp = client.post("/embed", json={"inputs": ["t1", "t2"]})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == _DENSE


def test_embed_empty_input_returns_empty_list(client: TestClient, server: BgeServer) -> None:
    """POST /embed with an empty list returns `[]` and never calls the engine."""
    resp = client.post("/embed", json={"inputs": []})

    assert resp.status_code == 200
    assert resp.json() == []
    cast(AsyncMock, server.runtime.engine.submit_embed_dense).assert_not_awaited()


# ── Test: /embed_all returns the exact {dense, sparse} shape via ORJSONResponse ─


def test_embed_all_returns_exact_shape(client: TestClient) -> None:
    """
    POST /embed_all still returns the exact ``{dense, sparse}`` shape and values (valid JSON,
    application/json) now that it's built via an explicit ORJSONResponse instead of constructing
    + validating an ``EmbedAllResponse``/``SparseToken`` model tree.
    """
    resp = client.post("/embed_all", json={"inputs": ["t1", "t2"]})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {
        "dense": _DENSE,
        "sparse": [[{"index": 5, "value": 0.5}], [{"index": 7, "value": 0.8}]],
    }


# ── Test: reranker gate (BGE_LOAD_RERANKER=false) ─────────────────────────────


def test_rerank_returns_503_when_reranker_not_loaded(client: TestClient, server: BgeServer) -> None:
    """
    POST /rerank returns a clean HTTP 503 "reranker not loaded" when BGE_LOAD_RERANKER=false
    (BgeModelsService.reranker_loaded is False) — never a crash, and the batching engine's
    rerank queue is never touched.
    """
    cast(MagicMock, server.runtime.models).reranker_loaded = False

    resp = client.post("/rerank", json={"query": "q", "texts": ["a", "b"]})

    assert resp.status_code == 503
    assert "reranker not loaded" in resp.json()["detail"]["error"]
    cast(AsyncMock, server.runtime.engine.submit_rerank).assert_not_awaited()


def test_embed_still_works_when_reranker_not_loaded(client: TestClient, server: BgeServer) -> None:
    """
    POST /embed is unaffected by the reranker gate — an embed-only deployment
    (BGE_LOAD_RERANKER=false) still serves dense embeddings normally.
    """
    cast(MagicMock, server.runtime.models).reranker_loaded = False

    resp = client.post("/embed", json={"inputs": ["t1", "t2"]})

    assert resp.status_code == 200
    assert resp.json() == _DENSE


def test_rerank_works_when_reranker_loaded(client: TestClient) -> None:
    """POST /rerank still serves normally when the reranker IS loaded (the default/gate=on path)."""
    resp = client.post("/rerank", json={"query": "q", "texts": ["a"]})

    assert resp.status_code == 200
    assert resp.json() == [{"index": 0, "score": 0.9}]
