# ====== Code Summary ======
# Unit tests for the AVX health guard (item 3). Two layers:
#   - CpuFeatures._probe_avx: parses /proc/cpuinfo flags, and degrades to "assume present" on any read
#     failure or missing flags line (never wrongly fails a host it cannot inspect).
#   - GET /health: reports 503 "unhealthy" when AVX is absent (PaddlePaddle would SIGILL on the first
#     inference), 503 "loading" while pipelines build, and 200 "ok" once ready.
# Paddle-free (CpuFeatures + a stubbed CONTEXT), so it runs on this AVX-less CPU.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.utils.cpu_features import CpuFeatures
from backend.routers import health_router


class _StubReadyService:
    """Minimal stand-in exposing only the `.ready` flag the health probe reads."""

    def __init__(self, ready: bool = True) -> None:
        self.ready = ready


def _client() -> TestClient:
    """A TestClient over a bare app with only the health router (no lifespan → no real build)."""
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


# ── CpuFeatures._probe_avx parsing ─────────────────────────────────────────────────


def test_probe_avx_true_when_flags_line_contains_avx(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme de avx sse4_2\n")
    assert _probe_over(cpuinfo) is True


def test_probe_avx_false_when_flags_line_lacks_avx(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nflags\t\t: fpu vme de sse4_2\n")
    assert _probe_over(cpuinfo) is False


def test_probe_avx_true_when_cpuinfo_is_unreadable(tmp_path: pathlib.Path) -> None:
    # A path that does not exist raises OSError on read → degrade to "assume present".
    assert _probe_over(tmp_path / "does_not_exist") is True


def test_probe_avx_true_when_no_flags_line(tmp_path: pathlib.Path) -> None:
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nmodel name\t: Some CPU\n")
    assert _probe_over(cpuinfo) is True


def _probe_over(path: pathlib.Path) -> bool:
    """Run the AVX probe against `path` via a subclass override (bypasses the process-wide cache)."""

    class _Probe(CpuFeatures):
        _CPUINFO_PATH = path

    return _Probe._probe_avx()


# ── GET /health ─────────────────────────────────────────────────────────────────


def test_health_reports_unhealthy_without_avx(monkeypatch) -> None:
    monkeypatch.setattr(CpuFeatures, "supports_avx", classmethod(lambda cls: False))
    response = _client().get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["ready"] is False
    assert "AVX" in body["detail"]


def test_health_reports_loading_while_pipelines_build(monkeypatch) -> None:
    monkeypatch.setattr(CpuFeatures, "supports_avx", classmethod(lambda cls: True))
    CONTEXT.ppstructure = _StubReadyService(ready=False)  # type: ignore[assignment]
    CONTEXT.paddleocr = _StubReadyService(ready=True)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "loading"


def test_health_reports_ok_when_avx_present_and_pipelines_ready(monkeypatch) -> None:
    monkeypatch.setattr(CpuFeatures, "supports_avx", classmethod(lambda cls: True))
    CONTEXT.ppstructure = _StubReadyService(ready=True)  # type: ignore[assignment]
    CONTEXT.paddleocr = _StubReadyService(ready=True)  # type: ignore[assignment]
    response = _client().get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ready"] is True
    assert body["detail"] is None
