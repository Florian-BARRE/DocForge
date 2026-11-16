# ====== Code Summary ======
# Unit tests for GET /health, served by the core HealthRoute through MineruServer: the `device` field
# the DocForge /capabilities probe reads (exactly "cpu" or "cuda"), the GPU gate (MINERU_REQUIRE_GPU
# with no visible CUDA device -> 503 "unhealthy"), and the always-ready service (the VLM loads lazily,
# so readiness is never gated on a model build). GPU-free: the device probe holds a fake detector.

# ====== Third-Party Library Imports ======
from fastapi.testclient import TestClient
from model_server_core import CudaDetector, DeviceProbe

# ====== Internal Project Imports ======
from backend import MineruServer
from config_loader import MineruServerConfig
from tests.support.mineru_app import build_server


class _FakeDetector(CudaDetector):
    """A GPU check with a fixed answer."""

    def __init__(self, cuda: bool) -> None:
        self._cuda = cuda

    def is_cuda_available(self) -> bool:
        return self._cuda


class _GpuNotRequiredConfig(MineruServerConfig):
    """A deliberate CPU wiring smoke-test (MINERU_REQUIRE_GPU=false)."""

    MINERU_REQUIRE_GPU = False


def _client(config: type[MineruServerConfig], cuda: bool) -> TestClient:
    """A TestClient over the real app (no lifespan → no real build) on a host with/without CUDA."""
    server: MineruServer = build_server(config=config)
    server.device_probe = DeviceProbe([_FakeDetector(cuda)])
    return TestClient(server.create_app())


def test_health_reports_device_when_ok() -> None:
    response = _client(_GpuNotRequiredConfig, cuda=False).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "ready": True, "detail": None, "device": "cpu"}


def test_health_reports_cuda_when_a_gpu_is_visible() -> None:
    response = _client(MineruServerConfig, cuda=True).get("/health")
    assert response.status_code == 200
    assert response.json()["device"] == "cuda"


def test_health_is_unhealthy_without_a_gpu_when_one_is_required() -> None:
    response = _client(MineruServerConfig, cuda=False).get("/health")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "ready": False,
        "detail": "No CUDA GPU visible; MinerU's VLM backend requires one.",
        "device": "cpu",
    }
