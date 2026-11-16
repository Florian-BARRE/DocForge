# ====== Code Summary ======
# Unit tests for the model_server_core adoption (R-27 step 4b): the PaddleServer lifecycle (the core
# lifespan validates the config, then drives the aggregate ModelService load/unload — the two eager
# pipelines are built at startup, the VL one lazily), the PaddleModelsService contract, the paddle
# detector injected alone into the core DeviceProbe (no NVIDIA driver node check), the historical PADDLE_*
# env var names kept on the shared config fields, the real-bool DEV_MODE parsing, and the thin
# entrypoint. PaddlePaddle-free: paddle is stubbed in sys.modules, the pipelines are fakes.

# ====== Standard Library Imports ======
import os
import subprocess
import sys
import types
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient
from model_server_core import CpuFeatureProbe, DeviceProbe, ModelService

# ====== Internal Project Imports ======
from backend import PaddleServer
from config_loader import PaddleServerConfig
from libs.paddle_models import PaddleCudaDetector, PaddleModelsService
from libs.paddleocr import PaddleOcrService
from libs.paddleocr_vl import PaddleOcrVlService
from libs.ppstructure import PpStructureService
from tests.support.paddle_app import FakePipeline, build_server


def _run_python(code: str, **env_overrides: str) -> str:
    """Evaluate `code` in a fresh interpreter (the config reads the env at class-evaluation time)."""
    env: dict[str, Any] = {**os.environ, **env_overrides}
    for name in ("DEVICE", "NUM_THREADS", "MAX_BODY_BYTES", "LOCK_WAIT_TIMEOUT_SECONDS"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class _FakeCpuFeatures:
    """A CPU-flag probe that always finds the flag."""

    def supports(self, flag: str) -> bool:
        return True


def _fake_paddle(*, compiled_with_cuda: bool, device_count: int) -> types.ModuleType:
    module = types.ModuleType("paddle")
    module.device = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_compiled_with_cuda=lambda: compiled_with_cuda,
        cuda=types.SimpleNamespace(device_count=lambda: device_count),
    )
    return module


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_the_real_services_are_model_services() -> None:
    server = PaddleServer(PaddleServerConfig)
    assert isinstance(server.model_service(), ModelService)
    assert isinstance(server.model_service(), PaddleModelsService)
    assert isinstance(server.ppstructure, PpStructureService)
    assert isinstance(server.paddleocr, PaddleOcrService)
    assert isinstance(server.paddleocr_vl, PaddleOcrVlService)
    assert all(isinstance(s, ModelService) for s in (server.ppstructure, server.paddleocr))


def test_the_services_are_not_ready_before_load_and_the_vl_one_never_gates_readiness() -> None:
    server = PaddleServer(PaddleServerConfig)
    assert server.models.ready is False
    assert server.paddleocr_vl.ready is False
    server.paddleocr_vl.load()  # lazy: nothing to build at startup
    assert server.paddleocr_vl.ready is False


def test_the_aggregate_is_ready_once_both_eager_pipelines_are_built() -> None:
    ppstructure, paddleocr = FakePipeline(False), FakePipeline(False)
    models = PaddleModelsService(ppstructure, paddleocr, FakePipeline(False))  # type: ignore[arg-type]
    assert models.ready is False
    ppstructure.load()
    assert models.ready is False
    paddleocr.load()
    assert models.ready is True


def test_lifespan_loads_every_pipeline_and_unloads_them_on_shutdown() -> None:
    ppstructure, paddleocr, paddleocr_vl = (
        FakePipeline(False),
        FakePipeline(False),
        FakePipeline(False),
    )
    server = build_server(ppstructure, paddleocr, paddleocr_vl)
    server.device_probe = DeviceProbe([])  # hermetic: never imports paddle
    server.cpu_features = _FakeCpuFeatures()  # type: ignore[assignment]

    with TestClient(server.create_app()) as client:
        assert (ppstructure.calls, paddleocr.calls, paddleocr_vl.calls) == (["load"],) * 3
        # Both eager pipelines are built by the lifespan, so the host reports ready.
        assert client.get("/health").json()["status"] == "ok"

    assert (ppstructure.calls, paddleocr.calls, paddleocr_vl.calls) == (["load", "unload"],) * 3


def test_a_failed_pipeline_build_still_unloads_every_pipeline() -> None:
    class _Boom(FakePipeline):
        def load(self) -> None:
            raise RuntimeError("model download failed")

    ppstructure, paddleocr, paddleocr_vl = FakePipeline(False), _Boom(False), FakePipeline(False)
    server = build_server(ppstructure, paddleocr, paddleocr_vl)

    with pytest.raises(RuntimeError, match="model download failed"):
        with TestClient(server.create_app()):
            pass

    assert ppstructure.calls == ["load", "unload"]
    assert paddleocr.calls == ["unload"]
    assert paddleocr_vl.calls == ["unload"]


def test_an_invalid_configuration_aborts_the_startup_before_any_build() -> None:
    class _BadTimeout(PaddleServerConfig):
        LOCK_WAIT_TIMEOUT_SECONDS = 0

    ppstructure = FakePipeline(False)
    server = build_server(ppstructure, config=_BadTimeout)

    with pytest.raises(ValueError, match="LOCK_WAIT_TIMEOUT_SECONDS"):
        with TestClient(server.create_app()):
            pass

    assert "load" not in ppstructure.calls


def test_unload_is_safe_before_anything_was_loaded() -> None:
    PaddleServer(PaddleServerConfig).models.unload()


def test_the_server_serves_the_three_routes_and_health() -> None:
    paths = set(PaddleServer(PaddleServerConfig).create_app().openapi()["paths"])
    assert paths == {"/health", "/layout-parsing", "/vl-parse", "/ocr"}


# ── Device detectors injected into the core DeviceProbe ───────────────────────


@pytest.mark.parametrize(
    ("compiled", "count", "expected"),
    [(True, 1, "cuda"), (True, 0, "cpu"), (False, 2, "cpu")],
)
def test_paddle_detector_needs_a_cuda_wheel_with_a_visible_device(
    monkeypatch: pytest.MonkeyPatch, compiled: bool, count: int, expected: str
) -> None:
    monkeypatch.setitem(
        sys.modules, "paddle", _fake_paddle(compiled_with_cuda=compiled, device_count=count)
    )
    assert DeviceProbe([PaddleCudaDetector()]).device().value == expected


def test_paddle_detector_degrades_to_cpu_when_paddle_is_not_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "paddle", None)  # `import paddle` raises ImportError
    assert DeviceProbe([PaddleCudaDetector()]).device().value == "cpu"


def test_server_asks_paddle_only() -> None:
    detectors = PaddleServer(PaddleServerConfig).device_probe._detectors
    assert [type(d) for d in detectors] == [PaddleCudaDetector]


def test_server_probes_the_cpu_for_avx() -> None:
    assert isinstance(PaddleServer(PaddleServerConfig).cpu_features, CpuFeatureProbe)


# ── Historical env var names on the shared config fields ──────────────────────


def test_shared_config_fields_keep_their_paddle_env_var_names() -> None:
    """PADDLE_MAX_BODY_BYTES feeds the core MAX_BODY_BYTES, PADDLE_LOCK_WAIT_TIMEOUT_SECONDS the
    core LOCK_WAIT_TIMEOUT_SECONDS; the defaults are the ones the service always had."""
    code = (
        "from config_loader import PaddleServerConfig as C; "
        "print(C.MAX_BODY_BYTES, C.LOCK_WAIT_TIMEOUT_SECONDS, C.SERVER_PORT, C.GZIP_MINIMUM_SIZE)"
    )
    assert _run_python(code).split() == ["104857600", "290.0", "80", "1024"]
    overridden = _run_python(
        code, PADDLE_MAX_BODY_BYTES="123", PADDLE_LOCK_WAIT_TIMEOUT_SECONDS="7"
    )
    assert overridden.split() == ["123", "7.0", "80", "1024"]


@pytest.mark.parametrize(("value", "expected"), [("false", "False"), ("true", "True")])
def test_dev_mode_is_parsed_as_a_real_bool(value: str, expected: str) -> None:
    """R-27 (approved behaviour change): DEV_MODE=false used to be truthy (any non-empty string)."""
    code = "from config_loader import PaddleServerConfig as C; print(C.DEV_MODE)"
    assert _run_python(code, DEV_MODE=value) == expected


# ── Entrypoint ────────────────────────────────────────────────────────────────


def test_entrypoint_exposes_the_assembled_asgi_app() -> None:
    code = (
        "import entrypoint; from fastapi import FastAPI; "
        "print(isinstance(entrypoint.app, FastAPI), entrypoint.app.title)"
    )
    assert _run_python(code) == "True PaddleOCR PP-StructureV3 layout-parsing service"
