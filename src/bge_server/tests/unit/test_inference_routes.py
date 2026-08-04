# ====== Code Summary ======
# Route-level tests for the inference router, focused on POST /embed_all. A bare FastAPI app mounts
# only the inference router (no lifespan, no model load); CONTEXT.batching_engine is replaced with a
# mock whose async methods return canned shapes. Asserts that /embed_all's `dense` sub-shape matches
# what /embed returns and its `sparse` sub-shape matches what /embed_sparse returns for the same
# input — the like-for-like contract the DocForge app relies on when it falls back to the two routes.

# ====== Standard Library Imports ======
from typing import cast
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers import inference_router
from config_loader import BgeServerConfig

# ── Fixtures ──────────────────────────────────────────────────────────────────

_DENSE = [[1.0, 2.0], [3.0, 4.0]]
_SPARSE_RAW = [[{"index": 5, "value": 0.5}], [{"index": 7, "value": 0.8}]]


@pytest.fixture
def client() -> TestClient:
    """
    Build a TestClient over a bare app mounting only the inference router, with a mocked engine.

    The batching engine is replaced with a mock whose submit_embed_dense / submit_embed_sparse /
    embed_all return canned shapes, so no model is loaded. CONTEXT.CONFIG points at the real config
    class (its class attributes drive request-size validation and max_length resolution).

    Returns:
        TestClient: Client bound to the router-only app.
    """
    app = FastAPI()
    app.include_router(inference_router)

    engine = MagicMock()
    engine.submit_embed_dense = AsyncMock(return_value=_DENSE)
    engine.submit_embed_sparse = AsyncMock(return_value=_SPARSE_RAW)
    engine.embed_all = AsyncMock(return_value=(_DENSE, _SPARSE_RAW))

    CONTEXT.CONFIG = BgeServerConfig
    CONTEXT.batching_engine = engine

    return TestClient(app)


# ── Test: /embed_all returns {dense, sparse} matching the two separate routes ──


def test_embed_all_shape_matches_separate_routes(client: TestClient) -> None:
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

    # embed_all is resolved with the config max_length (same value the dense/sparse workers use)
    cast(AsyncMock, CONTEXT.batching_engine.embed_all).assert_awaited_once_with(
        ["t1", "t2"], max_length=BgeServerConfig.BGE_M3_MAX_LENGTH
    )


# ── Test: empty input short-circuits without touching the engine ──────────────


def test_embed_all_empty_input(client: TestClient) -> None:
    """POST /embed_all with an empty list returns empty sub-lists and never calls the engine."""
    resp = client.post("/embed_all", json={"inputs": []})

    assert resp.status_code == 200
    assert resp.json() == {"dense": [], "sparse": []}
    cast(AsyncMock, CONTEXT.batching_engine.embed_all).assert_not_awaited()
