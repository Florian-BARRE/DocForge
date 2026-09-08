# ====== Code Summary ======
# Unit tests for GET /health, focused on the `device` field the DocForge /capabilities probe reads.
# The response must always carry `device`, and it must be exactly "cpu" or "cuda" (on this CPU CI/dev
# box GpuFeatures resolves to "cpu"). GPU-free (GpuFeatures monkeypatched + a stubbed CONFIG).

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.gpu_features import GpuFeatures
from backend.routers import health_router


class _StubConfig:
    """Minimal stand-in exposing only the GPU-requirement flag the health probe reads."""

    def __init__(self, require_gpu: bool) -> None:
        self.DOTS_OCR_REQUIRE_GPU = require_gpu


def _client() -> TestClient:
    """A TestClient over a bare app with only the health router (no lifespan → no real build)."""
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_health_reports_device_when_ok(monkeypatch) -> None:
    monkeypatch.setattr(GpuFeatures, "cuda_available", classmethod(lambda cls: False))
    CONTEXT.CONFIG = _StubConfig(require_gpu=False)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["device"] in {"cpu", "cuda"}


def test_health_reports_device_when_unhealthy(monkeypatch) -> None:
    monkeypatch.setattr(GpuFeatures, "cuda_available", classmethod(lambda cls: False))
    CONTEXT.CONFIG = _StubConfig(require_gpu=True)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["device"] in {"cpu", "cuda"}
