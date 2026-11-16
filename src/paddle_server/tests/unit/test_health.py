# ====== Code Summary ======
# Unit tests for the AVX health guard. Two layers:
#   - the core CpuFeatureProbe parses /proc/cpuinfo flags (paddle_server used to carry its own copy),
#     and degrades to "assume present" on any read failure or missing flags line (never wrongly fails a
#     host it cannot inspect).
#   - GET /health, served by the core HealthRoute through PaddleServer: 503 "unhealthy" when AVX is
#     absent (PaddlePaddle would SIGILL on the first inference), 503 "loading" while the eager
#     pipelines build, 200 "ok" once ready — and the lazy PaddleOCR-VL pipeline never gates readiness.
# Paddle-free (a fake detector + fake pipelines), so it runs on this AVX-less CPU.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient
from model_server_core import CpuFeatureProbe, CudaDetector, DeviceProbe

# ====== Internal Project Imports ======
from backend import PaddleServer
from tests.support.paddle_app import FakePipeline, build_server


class _FakeDetector(CudaDetector):
    """A GPU check with a fixed answer."""

    def __init__(self, cuda: bool) -> None:
        self._cuda = cuda

    def is_cuda_available(self) -> bool:
        return self._cuda


def _client(
    *,
    avx: bool = True,
    cuda: bool = False,
    ppstructure_ready: bool = True,
    paddleocr_ready: bool = True,
    paddleocr_vl_ready: bool = False,
) -> TestClient:
    """A TestClient over the real app (no lifespan → no real build) on a host with/without AVX."""
    server: PaddleServer = build_server(
        ppstructure=FakePipeline(ppstructure_ready),
        paddleocr=FakePipeline(paddleocr_ready),
        paddleocr_vl=FakePipeline(paddleocr_vl_ready),
    )
    server.device_probe = DeviceProbe([_FakeDetector(cuda)])
    server.cpu_features = _FakeCpuFeatures(avx)  # type: ignore[assignment]
    return TestClient(server.create_app())


class _FakeCpuFeatures:
    """A CPU-flag probe with a fixed answer for the `avx` flag."""

    def __init__(self, avx: bool) -> None:
        self._avx = avx

    def supports(self, flag: str) -> bool:
        assert flag == "avx"
        return self._avx


# ── CpuFeatureProbe parsing ────────────────────────────────────────────────────────


def test_probe_avx_true_when_flags_line_contains_avx(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme de avx sse4_2\n")
    assert CpuFeatureProbe(cpuinfo).supports("avx") is True


def test_probe_avx_false_when_flags_line_lacks_avx(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme de sse4_2\n")
    assert CpuFeatureProbe(cpuinfo).supports("avx") is False


def test_probe_avx_true_when_cpuinfo_is_unreadable(tmp_path: pathlib.Path) -> None:
    # A path that does not exist raises OSError on read → degrade to "assume present".
    assert CpuFeatureProbe(tmp_path / "does_not_exist").supports("avx") is True


def test_probe_avx_true_when_no_flags_line(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nmodel name\t: Some CPU\n")
    assert CpuFeatureProbe(cpuinfo).supports("avx") is True


# ── GET /health ─────────────────────────────────────────────────────────────────


def test_health_reports_unhealthy_without_avx() -> None:
    response = _client(avx=False).get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["ready"] is False
    assert (
        body["detail"] == "CPU lacks AVX support required by PaddlePaddle; inference would crash."
    )
    assert body["device"] in {"cpu", "cuda"}


def test_avx_gate_is_checked_before_pipeline_readiness() -> None:
    # Pipelines still building AND no AVX: the hard blocker wins ("unhealthy", not "loading").
    response = _client(avx=False, ppstructure_ready=False).get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


@pytest.mark.parametrize(
    ("ppstructure_ready", "paddleocr_ready"), [(False, True), (True, False), (False, False)]
)
def test_health_reports_loading_while_an_eager_pipeline_builds(
    ppstructure_ready: bool, paddleocr_ready: bool
) -> None:
    response = _client(ppstructure_ready=ppstructure_ready, paddleocr_ready=paddleocr_ready).get(
        "/health"
    )
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "loading"
    assert body["ready"] is False
    assert body["device"] in {"cpu", "cuda"}


def test_health_reports_ok_when_avx_present_and_pipelines_ready() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ready": True, "detail": None, "device": "cpu"}


def test_health_ok_does_not_wait_for_the_lazy_vl_pipeline() -> None:
    # PaddleOCR-VL builds on its first request: not built (ready False) must never keep the host out.
    assert _client(paddleocr_vl_ready=False).get("/health").status_code == 200


def test_health_reports_cuda_when_a_gpu_is_visible() -> None:
    assert _client(cuda=True).get("/health").json()["device"] == "cuda"
