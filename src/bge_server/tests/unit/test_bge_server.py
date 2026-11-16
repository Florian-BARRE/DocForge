# ====== Code Summary ======
# Unit tests for the model_server_core adoption (R-27 step 2): the BgeServer lifecycle (the async
# runtime nested in the core lifespan, with the shutdown order that protects the models), the
# BgeRuntime pieces (sub-batch auto rule, engine guard, partial-startup stop), the torch device
# detector injected into the core DeviceProbe, and the historical env var names kept on the shared
# config fields. Torch-free: the models are a recording fake, torch is stubbed in sys.modules.

# ====== Standard Library Imports ======
import os
import subprocess
import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ====== Third-Party Library Imports ======
import pytest
from fastapi.testclient import TestClient
from model_server_core import DeviceProbe

# ====== Internal Project Imports ======
from backend import BgeServer
from backend.runtime import CPU_AUTO_SUB_BATCH_SIZE, BgeRuntime
from config_loader import BgeServerConfig
from libs.bge_models import TorchCudaDetector
from tests.support.bge_app import build_server


class _NoKeepWarmConfig(BgeServerConfig):
    BGE_KEEPWARM_SECONDS = 0


class _RecordingModels:
    """A model service that records its lifecycle and answers the warmup calls."""

    ready = True
    reranker_loaded = False
    resolved_device = "cpu"
    use_fp16 = False
    max_concurrency = 1

    def __init__(self, events: list[str]) -> None:
        self._events = events

    def load(self) -> None:
        self._events.append("models.load")

    def unload(self) -> None:
        self._events.append("models.unload")

    def encode_dense(self, texts: list[str], max_length: int) -> list[list[float]]:
        return [[0.0] for _ in texts]

    encode_sparse = encode_colbert = encode_dense_sparse = encode_dense


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_lifespan_loads_models_then_starts_runtime_and_stops_runtime_before_unload() -> None:
    events: list[str] = []
    server = build_server(models=_RecordingModels(events), config=_NoKeepWarmConfig)
    runtime = server.runtime
    original_start, original_stop = runtime.start, runtime.stop

    async def start() -> None:
        events.append("runtime.start")
        await original_start()

    async def stop() -> None:
        events.append("runtime.stop")
        await original_stop()

    runtime.start, runtime.stop = start, stop  # type: ignore[method-assign]

    with TestClient(server.create_app()) as client:
        assert client.get("/health").status_code == 200
        assert runtime.engine is not None

    assert events == ["models.load", "runtime.start", "runtime.stop", "models.unload"]


def test_failed_runtime_start_still_stops_the_runtime_and_unloads_the_models() -> None:
    events: list[str] = []
    server = build_server(models=_RecordingModels(events), config=_NoKeepWarmConfig)

    async def failing_start() -> None:
        raise RuntimeError("engine could not start")

    async def stop() -> None:
        events.append("runtime.stop")

    server.runtime.start, server.runtime.stop = failing_start, stop  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="engine could not start"):
        with TestClient(server.create_app()):
            pass

    assert events == ["models.load", "runtime.stop", "models.unload"]


def test_invalid_config_aborts_startup_before_any_model_load() -> None:
    class _BadConfig(BgeServerConfig):
        BGE_MAX_BATCH_SIZE = 0

    events: list[str] = []
    server = build_server(models=_RecordingModels(events), config=_BadConfig)

    with pytest.raises(ValueError, match="BGE_MAX_BATCH_SIZE"):
        with TestClient(server.create_app()):
            pass

    assert "models.load" not in events


# ── BgeRuntime ────────────────────────────────────────────────────────────────


def _runtime(device: str | None, sub_batch: int) -> BgeRuntime:
    class _Config(BgeServerConfig):
        BGE_SUB_BATCH_SIZE = sub_batch

    models = MagicMock()
    models.resolved_device = device
    return BgeRuntime(_Config, models)


@pytest.mark.parametrize(
    ("device", "configured", "expected"),
    [
        ("cpu", 0, CPU_AUTO_SUB_BATCH_SIZE),  # auto on CPU: small sub-batches
        ("cuda", 0, 0),  # auto elsewhere: no splitting
        ("cpu", 4, 4),  # an explicit value always wins
    ],
)
def test_sub_batch_auto_rule(device: str, configured: int, expected: int) -> None:
    assert _runtime(device, configured)._resolve_sub_batch_size() == expected


def test_engine_is_a_loud_error_before_the_runtime_starts() -> None:
    with pytest.raises(RuntimeError, match="not started"):
        _ = _runtime("cpu", 0).engine


async def test_stop_after_a_partial_startup_is_a_safe_no_op() -> None:
    await _runtime("cpu", 0).stop()


async def test_stop_stops_the_keep_warm_task_before_the_engine() -> None:
    order: list[str] = []
    runtime = _runtime("cpu", 0)
    engine = MagicMock()
    engine.stop = AsyncMock(side_effect=lambda: order.append("engine"))
    keep_warm = MagicMock()
    keep_warm.stop = AsyncMock(side_effect=lambda: order.append("keep_warm"))
    runtime.engine = engine
    runtime._keep_warm = keep_warm

    await runtime.stop()

    assert order == ["keep_warm", "engine"]


# ── Torch device detector injected into the core DeviceProbe ──────────────────


def _fake_torch(cuda: bool) -> types.ModuleType:
    module = types.ModuleType("torch")
    module.cuda = types.SimpleNamespace(is_available=lambda: cuda)  # type: ignore[attr-defined]
    return module


@pytest.mark.parametrize(("cuda", "expected"), [(True, "cuda"), (False, "cpu")])
def test_device_probe_follows_torch(
    monkeypatch: pytest.MonkeyPatch, cuda: bool, expected: str
) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(cuda))
    assert DeviceProbe([TorchCudaDetector()]).device().value == expected


def test_device_probe_degrades_to_cpu_when_torch_is_not_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` raises ImportError
    assert DeviceProbe([TorchCudaDetector()]).device().value == "cpu"


def test_server_probes_the_device_through_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(True))
    assert BgeServer(BgeServerConfig).current_device() == "cuda"


# ── Historical env var names on the shared config fields ──────────────────────


def test_shared_config_fields_keep_their_bge_env_var_names() -> None:
    """BGE_DEVICE feeds the core DEVICE field, BGE_TORCH_NUM_THREADS the core NUM_THREADS."""
    code = (
        "from config_loader import BgeServerConfig as C; "
        "print(C.DEVICE, C.NUM_THREADS, C.SERVER_PORT, C.GZIP_MINIMUM_SIZE)"
    )
    env: dict[str, Any] = {**os.environ, "BGE_DEVICE": "cpu", "BGE_TORCH_NUM_THREADS": "3"}
    for name in ("DEVICE", "NUM_THREADS"):
        env.pop(name, None)

    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )

    assert result.stdout.split() == ["cpu", "3", "80", "1024"]


def test_an_unknown_device_policy_is_rejected_by_the_core_validation() -> None:
    class _BadDevice(BgeServerConfig):
        DEVICE = "tpu"

    with pytest.raises(ValueError, match="tpu"):
        _BadDevice.validate()
