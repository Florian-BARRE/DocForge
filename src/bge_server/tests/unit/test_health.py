# ====== Code Summary ======
# Unit tests for GET /health, focused on the `device` field the DocForge /capabilities probe reads.
# The response must always carry `device`, and it must be exactly "cpu" or "cuda" (on this CPU CI/dev
# box the DeviceProbe resolves to "cpu"). Torch-free (a stubbed CONTEXT), so it runs anywhere.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers import health_router


class _StubConfig:
    """Minimal stand-in exposing only the model IDs the health probe reads."""

    BGE_M3_MODEL = "BAAI/bge-m3"
    BGE_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class _StubModels:
    """Minimal stand-in exposing the loaded-model sentinels the health probe inspects."""

    def __init__(self, loaded: bool) -> None:
        self._embed_model = object() if loaded else None
        self._reranker = object() if loaded else None


def _client() -> TestClient:
    """A TestClient over a bare app with only the health router (no lifespan → no real load)."""
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_health_reports_device_when_ready() -> None:
    CONTEXT.CONFIG = _StubConfig  # type: ignore[assignment]
    CONTEXT.bge_models = _StubModels(loaded=True)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["device"] in {"cpu", "cuda"}


def test_health_reports_device_while_loading() -> None:
    CONTEXT.CONFIG = _StubConfig  # type: ignore[assignment]
    CONTEXT.bge_models = _StubModels(loaded=False)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "loading"
    assert body["device"] in {"cpu", "cuda"}
