# ====== Code Summary ======
# Unit tests for the model_server_core adoption (R-27 step 3): the MineruServer lifecycle (the core
# lifespan validates the config, then drives the ModelService load/unload; nothing is built at startup
# because the VLM loads lazily), the MineruService ModelService contract, the torch detector injected
# into the core DeviceProbe (after the NVIDIA driver one), the historical MINERU_* env var names kept
# on the shared config fields, the real-bool DEV_MODE parsing, and the thin entrypoint. GPU-free and
# torch-free: torch is stubbed in sys.modules.

# ====== Standard Library Imports ======
import os
import subprocess
import sys
import types
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient
from model_server_core import DeviceProbe, ModelService, NvidiaDriverDetector

# ====== Internal Project Imports ======
from backend import MineruServer
from config_loader import MineruServerConfig
from libs.mineru import MineruService, TorchCudaDetector
from tests.support.mineru_app import StubEngine, build_server


def _run_python(code: str, **env_overrides: str) -> str:
    """Evaluate `code` in a fresh interpreter (the config reads the env at class-evaluation time)."""
    env: dict[str, Any] = {**os.environ, **env_overrides}
    for name in ("DEVICE", "NUM_THREADS", "MAX_BODY_BYTES", "LOCK_WAIT_TIMEOUT_SECONDS"):
        env.pop(name, None)
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _fake_torch(cuda: bool) -> types.ModuleType:
    module = types.ModuleType("torch")
    module.cuda = types.SimpleNamespace(is_available=lambda: cuda)  # type: ignore[attr-defined]
    return module


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_the_service_is_a_model_service_that_is_ready_before_any_parse() -> None:
    server = build_server()
    assert isinstance(server.model_service(), ModelService)
    assert server.model_service() is server.service
    assert server.service.ready is True


def test_lifespan_loads_nothing_and_unloads_the_engine_on_shutdown() -> None:
    engine = StubEngine()
    unloaded: list[bool] = []
    engine.unload = lambda: unloaded.append(True)  # type: ignore[method-assign]
    server = build_server(engine)

    with TestClient(server.create_app()) as client:
        # Ready at once: the VLM loads lazily on the first /parse, so startup built nothing.
        assert engine.calls == []
        assert client.get("/health").status_code in {200, 503}

    assert unloaded == [True]


def test_an_invalid_configuration_aborts_the_startup() -> None:
    class _BadTimeout(MineruServerConfig):
        LOCK_WAIT_TIMEOUT_SECONDS = 0

    with pytest.raises(ValueError, match="LOCK_WAIT_TIMEOUT_SECONDS"):
        with TestClient(build_server(config=_BadTimeout).create_app()):
            pass


def test_unload_is_safe_before_anything_was_loaded() -> None:
    MineruService(
        backend="vlm-transformers",
        lang="ch",
        model_source="huggingface",
        model_cache_home="/models",
        lock_wait_timeout_seconds=1.0,
    ).unload()


# ── Device detectors injected into the core DeviceProbe ───────────────────────


@pytest.mark.parametrize(("cuda", "expected"), [(True, "cuda"), (False, "cpu")])
def test_torch_detector_follows_torch(
    monkeypatch: pytest.MonkeyPatch, cuda: bool, expected: str
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda))
    assert DeviceProbe([TorchCudaDetector()]).device().value == expected


def test_torch_detector_degrades_to_cpu_when_torch_is_not_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` raises ImportError
    assert DeviceProbe([TorchCudaDetector()]).device().value == "cpu"


def test_server_asks_the_driver_first_then_torch() -> None:
    detectors = MineruServer(MineruServerConfig).device_probe._detectors
    assert [type(d) for d in detectors] == [NvidiaDriverDetector, TorchCudaDetector]


# ── Historical env var names on the shared config fields ──────────────────────


def test_shared_config_fields_keep_their_mineru_env_var_names() -> None:
    """MINERU_MAX_BODY_BYTES feeds the core MAX_BODY_BYTES, MINERU_LOCK_WAIT_TIMEOUT_SECONDS the
    core LOCK_WAIT_TIMEOUT_SECONDS; the defaults are the ones the service always had."""
    code = (
        "from config_loader import MineruServerConfig as C; "
        "print(C.MAX_BODY_BYTES, C.LOCK_WAIT_TIMEOUT_SECONDS, C.SERVER_PORT, C.GZIP_MINIMUM_SIZE)"
    )
    assert _run_python(code).split() == ["104857600", "590.0", "80", "1024"]
    overridden = _run_python(
        code, MINERU_MAX_BODY_BYTES="123", MINERU_LOCK_WAIT_TIMEOUT_SECONDS="7"
    )
    assert overridden.split() == ["123", "7.0", "80", "1024"]


@pytest.mark.parametrize(("value", "expected"), [("false", "False"), ("true", "True")])
def test_dev_mode_is_parsed_as_a_real_bool(value: str, expected: str) -> None:
    """R-27 (approved behaviour change): DEV_MODE=false used to be truthy (any non-empty string)."""
    code = "from config_loader import MineruServerConfig as C; print(C.DEV_MODE)"
    assert _run_python(code, DEV_MODE=value) == expected


# ── Entrypoint ────────────────────────────────────────────────────────────────


def test_entrypoint_exposes_the_assembled_asgi_app() -> None:
    code = (
        "import entrypoint; from fastapi import FastAPI; "
        "print(isinstance(entrypoint.app, FastAPI), entrypoint.app.title)"
    )
    assert _run_python(code) == "True MinerU2.5-Pro VLM parse service"
