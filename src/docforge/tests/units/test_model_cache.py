# ====== Code Summary ======
# Unit tests for the process-level ModelCache and its application to the heavy local-model
# providers.  Verify the core property: the heavy loader runs ONCE across many provider
# instances for the same model-determining config, and a DIFFERENT config gets its own entry.

# ====== Standard Library Imports ======
from __future__ import annotations

import threading

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.providers.model_cache import ModelCache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Isolate every test from process-wide cache state (load + teardown)."""
    ModelCache.clear()
    yield
    ModelCache.clear()


# ─── Core cache semantics ────────────────────────────────────────────────────


def test_loader_invoked_once_for_same_key() -> None:
    """Many get_or_load calls on one key load the model exactly once and share it."""
    calls = {"n": 0}

    def loader() -> object:
        calls["n"] += 1
        return object()

    first = ModelCache.get_or_load(("m", False), loader)
    again = ModelCache.get_or_load(("m", False), loader)
    third = ModelCache.get_or_load(("m", False), loader)

    assert calls["n"] == 1
    assert first is again is third       # same shared instance returned every time


def test_distinct_keys_load_distinct_models() -> None:
    """Different model-determining keys each get their own loaded entry."""
    cpu = ModelCache.get_or_load(("m", False), lambda: "cpu-model")
    gpu = ModelCache.get_or_load(("m", True), lambda: "gpu-model")

    assert cpu == "cpu-model"
    assert gpu == "gpu-model"            # a GPU config never returns the CPU model


def test_loader_failure_is_not_cached() -> None:
    """A loader that raises propagates and leaves no cached entry (fail-closed)."""
    def boom() -> object:
        raise RuntimeError("model load failed")

    with pytest.raises(RuntimeError, match="model load failed"):
        ModelCache.get_or_load(("k",), boom)

    # A subsequent successful load for the same key still works (nothing was poisoned).
    ok = ModelCache.get_or_load(("k",), lambda: "recovered")
    assert ok == "recovered"


def test_concurrent_get_or_load_loads_once() -> None:
    """Concurrent threads requesting the same key trigger exactly one load."""
    calls = {"n": 0}
    barrier = threading.Barrier(8)

    def loader() -> object:
        calls["n"] += 1
        return object()

    results: list[object] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()  # maximize contention on the first access
        model = ModelCache.get_or_load(("shared",), loader)
        with lock:
            results.append(model)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1               # loaded exactly once despite 8 racing threads
    assert all(m is results[0] for m in results)


def test_lock_for_returns_stable_lock_per_key() -> None:
    """lock_for returns the same lock object for a key and distinct locks across keys."""
    a1 = ModelCache.lock_for(("x",))
    a2 = ModelCache.lock_for(("x",))
    b = ModelCache.lock_for(("y",))

    assert a1 is a2
    assert a1 is not b


# ─── Applied to the providers (loader invoked once across instances) ─────────


@pytest.mark.asyncio
async def test_docling_converter_loaded_once_across_instances(monkeypatch) -> None:
    """Two DoclingBackend instances (per-job rebuilds) share ONE converter load."""
    from common_libs.pipeline.bricks.providers.parser.docling.core import DoclingBackend

    calls = {"n": 0}
    sentinel = object()

    def fake_build(self) -> object:
        calls["n"] += 1
        return sentinel

    monkeypatch.setattr(DoclingBackend, "_build_converter", fake_build, raising=True)

    a = DoclingBackend(use_gpu=False)
    b = DoclingBackend(use_gpu=False)        # fresh instance, as the registry rebuilds per job
    assert a._get_converter() is sentinel
    assert b._get_converter() is sentinel
    assert calls["n"] == 1                    # converter built once, shared across instances

    # A different model-determining config (gpu) gets its own load.
    c = DoclingBackend(use_gpu=True)
    assert c._get_converter() is sentinel
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_vit_onnx_session_loaded_once_across_instances(monkeypatch) -> None:
    """Two VitOnnxClassifier instances share ONE ONNX session load for the same path+device."""
    from common_libs.pipeline.bricks.providers.classifier.vit_onnx.provider import VitOnnxClassifier

    calls = {"n": 0}

    class _FakeSession:
        def get_inputs(self):  # pragma: no cover - not exercised here
            raise NotImplementedError

    def fake_build(self) -> object:
        calls["n"] += 1
        return _FakeSession()

    monkeypatch.setattr(VitOnnxClassifier, "_build_session", fake_build, raising=True)

    a = VitOnnxClassifier(model_path="/models/vit.onnx", use_gpu=False)
    b = VitOnnxClassifier(model_path="/models/vit.onnx", use_gpu=False)
    s1 = ModelCache.get_or_load(a._model_key, a._build_session)
    s2 = ModelCache.get_or_load(b._model_key, b._build_session)

    assert s1 is s2
    assert calls["n"] == 1
