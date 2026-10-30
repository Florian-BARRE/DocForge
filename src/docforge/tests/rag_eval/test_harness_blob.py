"""The harness's benchmark blob against the CURRENT blob models — no stack, no network.

`DocForgeClient.chunk_blob` is driven through the real FastAPI app (a TestClient: the design and
stage routes are pure, the stores connect lazily), then its blob goes through the exact validation
POST /collections runs before any store touch. A harness override the pipeline's node configs no
longer accept (issue #223: `timeout_seconds` on the dense_sparse embed node) fails here, not as a
422 in the retrieval gate. Run with: `python -m pytest tests/rag_eval/test_harness_blob.py`."""

import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

from tests.rag_eval.harness import DocForgeClient

_APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"


@pytest.fixture(scope="module")
def app_modules():
    """The real app and its collection-blob helpers, imported once app/ is on sys.path."""
    if str(_APP_DIR) not in sys.path:
        sys.path.insert(0, str(_APP_DIR))
    from entrypoint import app  # noqa: PLC0415

    from backend.routers.collections.blob_helpers import CollectionBlobHelpers  # noqa: PLC0415

    return app, CollectionBlobHelpers


@pytest.fixture
def harness(app_modules, monkeypatch) -> DocForgeClient:
    """A DocForgeClient over the real app, auth off whatever the ambient .env says."""
    from config import RUNTIME_CONFIG  # noqa: PLC0415 — app/ is on sys.path by now

    monkeypatch.setattr(RUNTIME_CONFIG, "AUTH_ENABLED", False)
    monkeypatch.setattr(RUNTIME_CONFIG, "AUDIT_ENABLED", False)
    app, _ = app_modules
    return DocForgeClient("", "", http=TestClient(app, base_url="http://testserver/api/v1"))


@pytest.mark.parametrize(
    ("min_tokens", "target_tokens"),
    [(None, None), (0, None), (64, 256)],
    ids=["product-default", "strict", "custom"],
)
def test_chunk_blob_passes_collection_creation_validation(
    harness: DocForgeClient, app_modules, min_tokens: int | None, target_tokens: int | None
) -> None:
    blob = harness.chunk_blob(min_tokens, target_tokens)

    _, blob_helpers = app_modules
    blob_helpers.canonical_pipeline(blob)  # raises the 422 POST /collections would answer


def test_chunk_blob_keeps_its_cpu_safe_embed_overrides(harness: DocForgeClient) -> None:
    blob = harness.chunk_blob(0, None)

    nodes = {node["id"]: node.get("config", {}) for node in blob["nodes"]}
    assert nodes["chunk"]["min_tokens"] == 0
    assert nodes["embed"]["batch_size"] == 8
    assert nodes["embed"]["dense"]["timeout_seconds"] == 180.0
    assert "timeout_seconds" not in nodes["embed"]
