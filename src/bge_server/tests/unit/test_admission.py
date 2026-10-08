# ====== Code Summary ======
# Unit tests for bounded admission + abandoned-work dropping. BgeModelsService is mocked (no
# torch, no weights). Covers: a disconnected client's request is skipped (before enqueue, while
# queued, and between sub-batches), queue-full -> 503 + Retry-After, /health staying fast while
# inference is saturated, the global concurrency cap, and the small-request priority lane.

# ====== Standard Library Imports ======
import asyncio
import threading
import time
from typing import cast
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import httpx
import pytest
from fastapi import FastAPI, Request

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.routers import health_router, inference_router
from backend.routers.inference.helpers import ClientDisconnected, InferenceHelpers
from config_loader import BgeServerConfig
from libs.batching.engine import BatchingEngine
from libs.batching.models import QueueFullError


def _engine(models: MagicMock, **kwargs: int) -> BatchingEngine:
    params = {"max_batch_size": 32, "max_wait_ms": 0, "max_queue_size": 8}
    params.update(kwargs)
    return BatchingEngine(models=models, max_length=64, **params)


class _GatedModels:
    """Mock models whose encode_dense blocks on an Event and records call/concurrency stats."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.started = threading.Event()
        self.calls: list[list[str]] = []
        self._active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def _enter(self) -> None:
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)

    def _exit(self) -> None:
        with self._lock:
            self._active -= 1

    def encode_dense(self, texts: list[str], max_length: int) -> list[list[float]]:
        self._enter()
        try:
            self.calls.append(list(texts))
            self.started.set()
            self.release.wait(timeout=5)
            return [[0.0] for _ in texts]
        finally:
            self._exit()

    def compute_rerank_scores_flat(self, pairs: list[list[str]]) -> list[float]:
        self._enter()
        try:
            self.started.set()
            self.release.wait(timeout=5)
            return [0.5 for _ in pairs]
        finally:
            self._exit()


async def _wait_started(models: _GatedModels) -> None:
    for _ in range(200):
        if models.started.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("model call never started")


# ── Disconnect handling ───────────────────────────────────────────────────────


class _FakeRequest:
    """Request stub: is_disconnected flips True after ``after`` polls."""

    def __init__(self, after: int = 0) -> None:
        self._polls = 0
        self._after = after

    async def is_disconnected(self) -> bool:
        self._polls += 1
        return self._polls > self._after


async def test_already_disconnected_request_never_reaches_engine() -> None:
    ran = False

    async def engine_call() -> str:
        nonlocal ran
        ran = True
        return "x"

    with pytest.raises(ClientDisconnected):
        await InferenceHelpers.await_unless_disconnected(
            cast(Request, _FakeRequest(after=0)),
            engine_call(),
            0.01,
        )
    assert ran is False


async def test_disconnect_while_waiting_cancels_the_engine_call() -> None:
    cancelled = asyncio.Event()

    async def engine_call() -> str:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "x"

    with pytest.raises(ClientDisconnected):
        await InferenceHelpers.await_unless_disconnected(
            cast(Request, _FakeRequest(after=2)),
            engine_call(),
            0.01,
        )
    await asyncio.wait_for(cancelled.wait(), timeout=1)


async def test_queued_request_whose_client_left_is_dropped_without_running() -> None:
    models = _GatedModels()
    engine = _engine(models)  # type: ignore[arg-type]
    engine.start()
    try:
        first = asyncio.create_task(engine.submit_embed_dense(["running"]))
        await _wait_started(models)
        # Second request queues behind the in-flight batch, then its client disconnects.
        second = asyncio.create_task(engine.submit_embed_dense(["abandoned"]))
        await asyncio.sleep(0.05)
        second.cancel()
        models.release.set()
        await first
    finally:
        await engine.stop()
    assert models.calls == [["running"]]


async def test_abandoned_batch_stops_between_sub_batches() -> None:
    calls: list[list[str]] = []
    holder: dict[str, asyncio.Task] = {}
    loop = asyncio.get_running_loop()

    def encode_dense(texts: list[str], max_length: int) -> list[list[float]]:
        calls.append(list(texts))
        # The client disconnects while the first sub-batch is computing.
        loop.call_soon_threadsafe(holder["t"].cancel)
        time.sleep(0.1)
        return [[0.0] for _ in texts]

    models = MagicMock()
    models.encode_dense.side_effect = encode_dense
    engine = _engine(models, sub_batch_size=2)
    engine.start()
    try:
        holder["t"] = asyncio.create_task(engine.submit_embed_dense(["a", "b", "c", "d", "e", "f"]))
        with pytest.raises(asyncio.CancelledError):
            await holder["t"]
        await asyncio.sleep(0.3)
    finally:
        await engine.stop()
    assert calls == [["a", "b"]]


# ── Bounded admission ─────────────────────────────────────────────────────────


async def test_queue_full_rejects_immediately_with_queue_full_error() -> None:
    models = _GatedModels()
    engine = _engine(models, max_queue_size=1)  # type: ignore[arg-type]
    engine.start()
    tasks: list[asyncio.Task] = []
    try:
        tasks.append(asyncio.create_task(engine.submit_embed_dense(["running"])))
        await _wait_started(models)
        tasks.append(asyncio.create_task(engine.submit_embed_dense(["queued"])))
        await asyncio.sleep(0.05)
        tasks.append(asyncio.create_task(engine.submit_embed_dense(["queued2"])))
        await asyncio.sleep(0.05)
        t0 = time.perf_counter()
        with pytest.raises(QueueFullError):
            await engine.submit_embed_dense(["rejected"])
        assert time.perf_counter() - t0 < 0.5
    finally:
        models.release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.stop()


async def test_route_returns_503_with_retry_after_when_queue_full() -> None:
    app = FastAPI()
    app.include_router(inference_router)
    engine = MagicMock()

    async def full(_texts: list[str]) -> None:
        raise QueueFullError("full")

    engine.submit_embed_dense = full
    CONTEXT.CONFIG = BgeServerConfig
    CONTEXT.batching_engine = engine
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        resp = await client.post("/embed", json={"inputs": ["x"]})
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == str(BgeServerConfig.BGE_RETRY_AFTER_SECONDS)


async def test_health_stays_fast_while_inference_is_saturated() -> None:
    models = _GatedModels()
    engine = _engine(models, max_concurrent=1)  # type: ignore[arg-type]
    engine.start()
    stub = MagicMock()
    stub._embed_model = object()
    stub.reranker_loaded = True
    CONTEXT.CONFIG = BgeServerConfig
    CONTEXT.bge_models = stub
    CONTEXT.batching_engine = engine
    app = FastAPI()
    app.include_router(inference_router)
    app.include_router(health_router)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as client:
            # Warm the one-off device probe (lazy torch import) so only load is measured.
            await client.get("/health")
            busy = asyncio.create_task(client.post("/embed", json={"inputs": ["a"] * 4}))
            await _wait_started(models)
            t0 = time.perf_counter()
            health = await client.get("/health")
            elapsed = time.perf_counter() - t0
            assert health.status_code == 200
            assert elapsed < 0.5
            models.release.set()
            assert (await busy).status_code == 200
    finally:
        models.release.set()
        await engine.stop()


# ── Concurrency cap + priority lane ───────────────────────────────────────────


@pytest.mark.parametrize(("cap", "expected_peak"), [(1, 1), (2, 2)])
async def test_max_concurrent_caps_simultaneous_forward_passes(
    cap: int, expected_peak: int
) -> None:
    models = _GatedModels()
    engine = _engine(models, max_concurrent=cap)  # type: ignore[arg-type]
    engine.start()
    try:
        dense = asyncio.create_task(engine.submit_embed_dense(["a"]))
        rerank = asyncio.create_task(engine.submit_rerank("q", ["t"]))
        await asyncio.sleep(0.2)
        assert models.peak == expected_peak
        models.release.set()
        await asyncio.gather(dense, rerank)
    finally:
        models.release.set()
        await engine.stop()
    assert models.peak == expected_peak


async def test_small_request_is_served_before_queued_bulk() -> None:
    models = _GatedModels()
    engine = _engine(models, small_max_items=2)  # type: ignore[arg-type]
    engine.start()
    try:
        running = asyncio.create_task(engine.submit_embed_dense(["running"] * 8))
        await _wait_started(models)
        bulk = asyncio.create_task(engine.submit_embed_dense(["bulk"] * 8))
        await asyncio.sleep(0.05)
        query = asyncio.create_task(engine.submit_embed_dense(["query"]))
        await asyncio.sleep(0.05)
        models.release.set()
        await asyncio.gather(running, bulk, query)
    finally:
        await engine.stop()
    assert [c[0] for c in models.calls] == ["running", "query", "bulk"]
