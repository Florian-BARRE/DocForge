"""Shared-embedder limiter: Redis lease semaphore (fakeredis), TTL expiry, no-op default, node wiring,
parse-memory fallback, endpoint normalisation."""

import asyncio
import time

import fakeredis
import httpx
import pytest
from limiter.redis_provider_limiter import KEY_PREFIX, RedisProviderLimiter

from shared_libs.pipelines.base import (
    EndpointKey,
    NoOpProviderLimiter,
    ProviderLimiterRegistry,
    ProviderSlotTimeout,
)
from shared_libs.pipelines.ingest.nodes.parse.parser.docling_base.subprocess import (
    ParseMemoryFallback,
)
from shared_libs.pipelines.nodes.embed.base import BaseEmbedConfig, BaseEmbedderNode, EmbedConsumes
from shared_libs.pipelines.nodes.embed.bge_server import EmbedBgeServerConfig, EmbedBgeServerNode
from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.public_models import Chunk, CollectionContract

ENDPOINT = "http://bge:80"


@pytest.fixture(autouse=True)
def _reset():
    yield
    ProviderLimiterRegistry.reset()
    ParseMemoryFallback.install(0)


def _two_workers(server: fakeredis.FakeServer, limit: int):
    """Two limiters = two worker processes sharing one Redis."""
    return [
        RedisProviderLimiter(
            fakeredis.FakeAsyncRedis(server=server), default_limit=limit, poll_seconds=0.01
        )
        for _ in range(2)
    ]


async def test_cap_enforced_across_two_workers() -> None:
    server = fakeredis.FakeServer()
    workers = _two_workers(server, limit=2)
    inflight = peak = 0

    async def job(limiter) -> None:
        nonlocal inflight, peak
        async with limiter.slot(ENDPOINT, lease_seconds=30):
            inflight += 1
            peak = max(peak, inflight)
            await asyncio.sleep(0.05)
            inflight -= 1

    await asyncio.gather(*(job(workers[i % 2]) for i in range(8)))
    assert peak == 2


async def test_release_frees_the_slot_even_on_error() -> None:
    server = fakeredis.FakeServer()
    (limiter, _) = _two_workers(server, limit=1)
    with pytest.raises(RuntimeError):
        async with limiter.slot(ENDPOINT):
            raise RuntimeError("boom")
    redis = fakeredis.FakeAsyncRedis(server=server)
    assert await redis.zcard(KEY_PREFIX + ENDPOINT) == 0


async def test_lease_ttl_expiry_unblocks_a_crashed_holder() -> None:
    server = fakeredis.FakeServer()
    (limiter, _) = _two_workers(server, limit=1)
    redis = fakeredis.FakeAsyncRedis(server=server)
    # A crashed worker: a lease whose EXPIRY (the score) is already past, never released.
    await redis.zadd(KEY_PREFIX + ENDPOINT, {"dead": time.time() - 100})
    start = time.monotonic()
    async with limiter.slot(ENDPOINT, lease_seconds=30):
        assert time.monotonic() - start < 1
        assert await redis.zcard(KEY_PREFIX + ENDPOINT) == 1  # dead lease purged, ours held


async def test_per_call_override_beats_default() -> None:
    server = fakeredis.FakeServer()
    (limiter, _) = _two_workers(server, limit=5)
    async with limiter.slot(ENDPOINT, max_inflight=1):
        with pytest.raises(asyncio.TimeoutError):
            async with asyncio.timeout(0.1):
                async with limiter.slot(ENDPOINT, max_inflight=1):
                    pass


async def test_wait_budget_spent_raises_instead_of_proceeding_without_a_slot() -> None:
    """M-4: past the wait budget the call RAISES ProviderSlotTimeout — proceeding slot-less would
    disable the cap exactly under overload. The give-up leaves no waiter entry behind."""
    server = fakeredis.FakeServer()
    limiter = RedisProviderLimiter(
        fakeredis.FakeAsyncRedis(server=server),
        default_limit=1,
        poll_seconds=0.01,
        max_wait_seconds=0.05,
    )
    entered = False
    async with limiter.slot(ENDPOINT, lease_seconds=30):
        with pytest.raises(ProviderSlotTimeout):
            async with limiter.slot(ENDPOINT):
                entered = True
    assert not entered
    redis = fakeredis.FakeAsyncRedis(server=server)
    assert await redis.zcard(KEY_PREFIX + ENDPOINT + ":queue") == 0


async def test_redis_outage_fails_open() -> None:
    """Only a Redis error fails open: the guarded call still runs."""
    server = fakeredis.FakeServer()
    server.connected = False
    limiter = RedisProviderLimiter(
        fakeredis.FakeAsyncRedis(server=server), default_limit=1, poll_seconds=0.01
    )
    ran = False
    async with limiter.slot(ENDPOINT):
        ran = True
    assert ran


async def test_mixed_leases_never_exceed_the_cap() -> None:
    """H-1: a short-lease caller must never evict a longer holder's live lease. The old purge used
    the CALLER's lease (score = acquisition time), so a lease-0.2 newcomer purged a lease-30 holder
    acquired >0.2 s earlier and the cap was exceeded."""
    server = fakeredis.FakeServer()
    workers = _two_workers(server, limit=2)
    inflight = peak = 0

    async def job(limiter, lease: float, hold: float) -> None:
        nonlocal inflight, peak
        async with limiter.slot(ENDPOINT, lease_seconds=lease):
            inflight += 1
            peak = max(peak, inflight)
            await asyncio.sleep(hold)
            inflight -= 1

    # Two long holders take the endpoint for 0.6 s; short-lease callers keep knocking meanwhile.
    long_holders = [asyncio.create_task(job(workers[i], 30.0, 0.6)) for i in range(2)]
    await asyncio.sleep(0.05)
    short = [job(workers[i % 2], 0.2, 0.05) for i in range(6)]
    await asyncio.gather(*long_holders, *short)
    assert peak == 2


async def test_scores_use_the_redis_server_clock_not_the_local_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """M-3: a worker whose local clock is far behind must not rank ahead of live holders."""
    server = fakeredis.FakeServer()
    (fast, slow) = _two_workers(server, limit=1)
    async with fast.slot(ENDPOINT, lease_seconds=30):
        monkeypatch.setattr(time, "time", lambda: 0.0)  # a skewed worker clock
        with pytest.raises(asyncio.TimeoutError):
            async with asyncio.timeout(0.2):
                async with slow.slot(ENDPOINT, lease_seconds=30):
                    pass


async def test_a_timed_out_call_keeps_its_slot_until_the_lease_expires() -> None:
    """H-2: a client timeout abandons a request the CPU embedder keeps computing — its slot is held
    until the lease expires instead of being handed to the next (split) request immediately."""
    server = fakeredis.FakeServer()
    (limiter, other) = _two_workers(server, limit=1)
    redis = fakeredis.FakeAsyncRedis(server=server)
    with pytest.raises(httpx.ReadTimeout):
        async with limiter.slot(ENDPOINT, lease_seconds=0.4):
            raise httpx.ReadTimeout("abandoned")
    assert await redis.zcard(KEY_PREFIX + ENDPOINT) == 1  # still held
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.15):
            async with other.slot(ENDPOINT, lease_seconds=5):
                pass
    start = time.monotonic()
    async with other.slot(ENDPOINT, lease_seconds=5):  # admitted once the lease expired
        assert time.monotonic() - start < 1.0


async def test_an_error_before_sending_releases_the_slot_at_once() -> None:
    """A connect failure never reached the provider — the slot is released immediately."""
    server = fakeredis.FakeServer()
    (limiter, _) = _two_workers(server, limit=1)
    redis = fakeredis.FakeAsyncRedis(server=server)
    for error in (httpx.ConnectError("refused"), httpx.PoolTimeout("pool")):
        with pytest.raises(type(error)):
            async with limiter.slot(ENDPOINT, lease_seconds=30):
                raise error
        assert await redis.zcard(KEY_PREFIX + ENDPOINT) == 0


async def test_cancellation_during_acquire_leaves_no_ghost_member() -> None:
    """L-1: a cancel landing after Redis applied the admission but before the reply was read must
    not leave a lease (or waiter entry) pinning capacity."""
    server = fakeredis.FakeServer()
    (limiter, _) = _two_workers(server, limit=1)
    redis = fakeredis.FakeAsyncRedis(server=server)
    original = limiter._store.try_admit

    async def admitted_then_cancelled(*args, **kwargs):
        await original(*args, **kwargs)
        raise asyncio.CancelledError

    limiter._store.try_admit = admitted_then_cancelled
    with pytest.raises(asyncio.CancelledError):
        async with limiter.slot(ENDPOINT, lease_seconds=30):
            pass
    assert await redis.zcard(KEY_PREFIX + ENDPOINT) == 0
    assert await redis.zcard(KEY_PREFIX + ENDPOINT + ":queue") == 0


async def test_admission_is_fifo() -> None:
    """The oldest live waiter is admitted first (no starvation by a luckier poller)."""
    server = fakeredis.FakeServer()
    (limiter, other) = _two_workers(server, limit=1)
    order: list[str] = []

    async def waiter(name: str, which) -> None:
        async with which.slot(ENDPOINT, lease_seconds=30):
            order.append(name)

    async with limiter.slot(ENDPOINT, lease_seconds=30):
        first = asyncio.create_task(waiter("first", other))
        await asyncio.sleep(0.05)
        second = asyncio.create_task(waiter("second", limiter))
        await asyncio.sleep(0.05)
    await asyncio.gather(first, second)
    assert order == ["first", "second"]


async def test_noop_when_unbound() -> None:
    assert isinstance(ProviderLimiterRegistry.current(), NoOpProviderLimiter)
    async with ProviderLimiterRegistry.current().slot("x", max_inflight=1):
        async with ProviderLimiterRegistry.current().slot("x", max_inflight=1):
            pass


def test_endpoint_normalisation() -> None:
    assert EndpointKey.normalize("HTTP://Bge:80/") == "http://bge:80"
    assert EndpointKey.normalize("http://bge/") == "http://bge:80"
    assert EndpointKey.normalize("https://api.x.com/v1") == "https://api.x.com:443"


class _Recorder(NoOpProviderLimiter):
    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, float]] = []

    def slot(self, endpoint, *, max_inflight=None, lease_seconds=60.0):
        self.calls.append((endpoint, max_inflight, lease_seconds))
        return super().slot(endpoint, max_inflight=max_inflight, lease_seconds=lease_seconds)


async def test_embed_node_goes_through_the_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    ProviderLimiterRegistry.install(recorder)

    def handler(request: httpx.Request) -> httpx.Response:
        import json  # noqa: PLC0415

        inputs = json.loads(request.content)["inputs"]
        if request.url.path == "/embed":
            return httpx.Response(200, json=[[0.1] * 4 for _ in inputs])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **k: original(*a, **{**k, "transport": transport})
    )
    await HttpClientPool.shutdown()
    node = EmbedBgeServerNode(
        id="e",
        config=EmbedBgeServerConfig(
            base_url="http://BGE:80/", model="m", embed_sparse=False, max_concurrency=1
        ),
    )
    contract = CollectionContract(
        collection_id=__import__("uuid").uuid4(),
        name="c",
        supported_formats=["pdf"],
        max_file_size_bytes=1,
        fields=[],
    )
    chunks = [Chunk(chunk_id="d#c0", ordinal=0, text="hello world")]
    await node.run(EmbedConsumes(chunks=chunks, contract=contract))
    assert recorder.calls and all(call[0] == "http://bge:80" for call in recorder.calls)
    assert recorder.calls[0][1] == 1  # the per-collection override rides along
    assert recorder.calls[0][2] == 60.0 + 15.0  # lease = request timeout + margin


def test_max_concurrency_validated_and_forbid() -> None:
    assert BaseEmbedConfig(model="m").max_concurrency is None
    with pytest.raises(ValueError):
        BaseEmbedConfig(model="m", max_concurrency=0)
    assert issubclass(EmbedBgeServerNode, BaseEmbedderNode)


def test_parse_memory_fallback() -> None:
    ParseMemoryFallback.install(4096)
    assert ParseMemoryFallback.resolve(0) == 4096  # unset -> deployment fallback
    assert ParseMemoryFallback.resolve(2048) == 2048  # collection override wins
    assert ParseMemoryFallback.resolve(0, applies=False) == 0  # granite/CUDA keeps its own
    ParseMemoryFallback.install(0)
    assert ParseMemoryFallback.resolve(0) == 0


class _AlwaysSaturated(NoOpProviderLimiter):
    def __init__(self) -> None:
        self.calls = 0

    def slot(self, endpoint, *, max_inflight=None, lease_seconds=60.0):
        self.calls += 1
        raise ProviderSlotTimeout("saturated")


async def test_slot_timeout_is_retried_with_backoff_but_never_split() -> None:
    """M-4: the embed node treats a slot timeout as transient (retry) but never splits the batch —
    halves would only queue behind the same saturated endpoint."""
    limiter = _AlwaysSaturated()
    ProviderLimiterRegistry.install(limiter)
    node = EmbedBgeServerNode(
        id="e",
        config=EmbedBgeServerConfig(
            base_url="http://bge:80",
            model="m",
            embed_sparse=False,
            max_retries=2,
            retry_backoff_seconds=0,
        ),
    )
    contract = CollectionContract(
        collection_id=__import__("uuid").uuid4(),
        name="c",
        supported_formats=["pdf"],
        max_file_size_bytes=1,
        fields=[],
    )
    chunks = [Chunk(chunk_id=f"d#c{i}", ordinal=i, text=f"text {i}") for i in range(4)]
    with pytest.raises(ProviderSlotTimeout):
        await node.run(EmbedConsumes(chunks=chunks, contract=contract))
    assert limiter.calls == 3  # 1 + max_retries on the SAME 4-text batch, no halves
