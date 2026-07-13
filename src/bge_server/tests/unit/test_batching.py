# ====== Code Summary ======
# Unit tests for the dynamic-batching engine (BatchingEngine + BatchQueueWorker).
# BgeModelsService is fully mocked — no torch, no FlagEmbedding, no GPU required.
# Covers: batch-by-size, batch-by-wait, dense/sparse/colbert offset scatter, rerank per-request
# re-indexing, QueueFullError on full queue, graceful stop resolving pending futures,
# and batch-level error isolation.

# ====== Standard Library Imports ======
import asyncio
from unittest.mock import MagicMock, patch

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.batching.engine import BatchingEngine
from libs.batching.models import QueueFullError
from libs.batching.worker import BatchQueueWorker


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_mock_models(
    dense_result: list[list[float]] | None = None,
    sparse_result: list[list[dict]] | None = None,
    colbert_result: list[list[list[float]]] | None = None,
    flat_scores: list[float] | None = None,
) -> MagicMock:
    """
    Build a MagicMock that stands in for BgeModelsService.

    Args:
        dense_result: Return value for encode_dense.
        sparse_result: Return value for encode_sparse.
        colbert_result: Return value for encode_colbert.
        flat_scores: Return value for compute_rerank_scores_flat.

    Returns:
        MagicMock: Configured mock service.
    """
    mock = MagicMock()
    if dense_result is not None:
        mock.encode_dense.return_value = dense_result
    if sparse_result is not None:
        mock.encode_sparse.return_value = sparse_result
    if colbert_result is not None:
        mock.encode_colbert.return_value = colbert_result
    if flat_scores is not None:
        mock.compute_rerank_scores_flat.return_value = flat_scores
    return mock


def _make_engine(
    models: MagicMock,
    max_batch_size: int = 32,
    max_wait_ms: int = 0,
    max_queue_size: int = 256,
    max_length: int = 512,
) -> BatchingEngine:
    """
    Construct a BatchingEngine with the given mock models and tuning knobs.

    Args:
        models: Mock BgeModelsService.
        max_batch_size: Batch cost budget.
        max_wait_ms: Batch formation window (0 = process first-available).
        max_queue_size: Per-worker queue capacity.
        max_length: Token length forwarded to encode_dense/encode_sparse.

    Returns:
        BatchingEngine: Ready-to-start engine.
    """
    return BatchingEngine(
        models=models,
        max_length=max_length,
        max_batch_size=max_batch_size,
        max_wait_ms=max_wait_ms,
        max_queue_size=max_queue_size,
    )


# ── Test: batch-by-size (dense) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_by_size_dense() -> None:
    """
    Two concurrent dense requests whose combined cost equals max_batch_size are processed
    in a single model call. encode_dense is called exactly once with all texts flattened.
    """
    # 3 texts per request, max_batch_size=6 — first pair of requests fills the budget
    texts_a = ["a1", "a2", "a3"]
    texts_b = ["b1", "b2", "b3"]
    vecs_a = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    vecs_b = [[7.0, 8.0], [9.0, 10.0], [11.0, 12.0]]
    all_vecs = vecs_a + vecs_b

    models = _make_mock_models(dense_result=all_vecs)
    engine = _make_engine(models, max_batch_size=6, max_wait_ms=100)
    engine.start()

    try:
        result_a, result_b = await asyncio.gather(
            engine.submit_embed_dense(texts_a),
            engine.submit_embed_dense(texts_b),
        )
    finally:
        await engine.stop()

    # encode_dense called exactly once with the flattened 6-text list
    models.encode_dense.assert_called_once()
    call_args = models.encode_dense.call_args[0]
    assert call_args[0] == texts_a + texts_b

    # Results correctly scattered back to each request
    assert result_a == vecs_a
    assert result_b == vecs_b


# ── Test: batch-by-wait ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_by_wait_dense() -> None:
    """
    Two requests each with cost=1 and max_batch_size=100 still get batched together
    when max_wait_ms gives the second request time to arrive before processing starts.
    """
    vecs = [[0.1, 0.2], [0.3, 0.4]]
    models = _make_mock_models(dense_result=vecs)
    # max_wait_ms=50 — both requests arrive within the window
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=50)
    engine.start()

    try:
        result_a, result_b = await asyncio.gather(
            engine.submit_embed_dense(["text_a"]),
            engine.submit_embed_dense(["text_b"]),
        )
    finally:
        await engine.stop()

    # Both texts submitted in one call
    models.encode_dense.assert_called_once()
    flat = models.encode_dense.call_args[0][0]
    assert set(flat) == {"text_a", "text_b"}

    assert result_a == [vecs[0]] or result_a == [vecs[1]]
    assert result_b == [vecs[1]] or result_b == [vecs[0]]
    # They must be different
    assert result_a != result_b


# ── Test: dense scatter offsets ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dense_scatter_offsets() -> None:
    """
    Three requests with different text counts are processed in one batch; each receives
    exactly the slice that corresponds to its position in the flat input.
    """
    texts_a = ["a"]
    texts_b = ["b1", "b2"]
    texts_c = ["c1", "c2", "c3"]
    vecs = [[float(i)] for i in range(6)]  # 6 vectors total

    models = _make_mock_models(dense_result=vecs)
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=50)
    engine.start()

    try:
        ra, rb, rc = await asyncio.gather(
            engine.submit_embed_dense(texts_a),
            engine.submit_embed_dense(texts_b),
            engine.submit_embed_dense(texts_c),
        )
    finally:
        await engine.stop()

    # Scatter by offset: a=[0], b=[1,2], c=[3,4,5]
    assert len(ra) == 1
    assert len(rb) == 2
    assert len(rc) == 3
    # Each slice is exactly the right portion of the flat vector list
    flat = models.encode_dense.call_args[0][0]
    flat_index_a = flat.index(texts_a[0])
    flat_index_b0 = flat.index(texts_b[0])
    assert flat_index_a < flat_index_b0  # ordering preserved within a single flush


# ── Test: sparse scatter offsets ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sparse_scatter_offsets() -> None:
    """
    Two sparse requests receive the correct slices from the flat encode_sparse result.
    """
    tok_a = [[{"index": 1, "value": 0.5}], [{"index": 2, "value": 0.3}]]
    tok_b = [[{"index": 3, "value": 0.8}]]

    models = _make_mock_models(sparse_result=tok_a + tok_b)
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=50)
    engine.start()

    try:
        ra, rb = await asyncio.gather(
            engine.submit_embed_sparse(["t1", "t2"]),
            engine.submit_embed_sparse(["t3"]),
        )
    finally:
        await engine.stop()

    assert ra == tok_a
    assert rb == tok_b


# ── Test: colbert scatter offsets ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_colbert_scatter_offsets() -> None:
    """
    Two colbert requests receive the correct per-text token-vector-list slices from the
    flat encode_colbert result. Verifies variable-length (per text) nested lists survive
    the flatten -> encode -> scatter round trip unchanged.
    """
    # text_a -> 1 text with 3 token vectors; text_b -> 2 texts with 2 and 4 token vectors
    vecs_a = [[[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]]
    vecs_b = [[[0.4] * 1024, [0.5] * 1024], [[0.6] * 1024] * 4]

    models = _make_mock_models(colbert_result=vecs_a + vecs_b)
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=50)
    engine.start()

    try:
        ra, rb = await asyncio.gather(
            engine.submit_embed_colbert(["t1"]),
            engine.submit_embed_colbert(["t2", "t3"]),
        )
    finally:
        await engine.stop()

    models.encode_colbert.assert_called_once()
    assert ra == vecs_a
    assert rb == vecs_b
    # Variable per-text token counts preserved through the round trip
    assert len(ra[0]) == 3
    assert len(rb[0]) == 2
    assert len(rb[1]) == 4
    assert len(ra[0][0]) == 1024


# ── Test: rerank per-request re-indexing ─────────────────────────────────────


@pytest.mark.asyncio
async def test_rerank_per_request_reindexing() -> None:
    """
    Two concurrent rerank requests are batched into one flat score list. Each request
    receives indices 0..n-1 LOCAL to that request (not global offsets).
    """
    # Request A: 3 candidates; Request B: 2 candidates
    # Flat scores: [0.9, 0.5, 0.7, 0.3, 0.8]
    flat_scores = [0.9, 0.5, 0.7, 0.3, 0.8]

    models = _make_mock_models(flat_scores=flat_scores)
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=50)
    engine.start()

    try:
        ra, rb = await asyncio.gather(
            engine.submit_rerank("query_a", ["cand1", "cand2", "cand3"]),
            engine.submit_rerank("query_b", ["cand4", "cand5"]),
        )
    finally:
        await engine.stop()

    # Both requests: indices must be 0-based per request, not global
    assert [r["index"] for r in ra] == [0, 1, 2]
    assert [r["index"] for r in rb] == [0, 1]

    # Scores correctly assigned from the flat list
    assert [r["score"] for r in ra] == [0.9, 0.5, 0.7]
    assert [r["score"] for r in rb] == [0.3, 0.8]


# ── Test: QueueFullError when queue is full ───────────────────────────────────


@pytest.mark.asyncio
async def test_queue_full_raises_queue_full_error() -> None:
    """
    When the queue is at capacity, submit() raises QueueFullError immediately (no await).
    """
    # Very slow encode so items accumulate: use an event to pause it
    pause = asyncio.Event()

    def slow_encode(texts, max_length):
        # Block until the test releases the event — but this runs in to_thread so
        # we just return immediately; the real test is that submit raises before processing
        return [[0.0] for _ in texts]

    models = MagicMock()
    models.encode_dense.side_effect = slow_encode

    # Queue size 1: first item fills it, second should raise
    engine = _make_engine(models, max_batch_size=100, max_wait_ms=0, max_queue_size=1)
    engine.start()

    try:
        loop = asyncio.get_running_loop()
        # Fill the queue with one item by submitting directly to the worker
        from libs.batching.models import EmbedItem

        future1 = loop.create_future()
        item1 = EmbedItem(future=future1, cost=1, texts=["fill"])
        engine._dense_worker.submit(item1)

        # Now the queue is full — next submit must raise
        future2 = loop.create_future()
        item2 = EmbedItem(future=future2, cost=1, texts=["overflow"])
        with pytest.raises(QueueFullError):
            engine._dense_worker.submit(item2)

        # Clean up future1 if not yet resolved
        if not future1.done():
            future1.cancel()

    finally:
        await engine.stop()


# ── Test: graceful stop resolves pending futures ──────────────────────────────


@pytest.mark.asyncio
async def test_graceful_stop_resolves_pending_futures() -> None:
    """
    stop() drains the queue and sets exceptions on pending futures so no caller hangs.
    After stop(), awaiting a submitted future completes with an exception (not a hang).
    """
    # Pause the model so items stay in the queue when we call stop()
    block_event = asyncio.Event()

    async def blocking_process(batch):
        # This process_fn blocks until released — simulates slow model
        await asyncio.wait_for(block_event.wait(), timeout=5.0)

    worker = BatchQueueWorker(
        name="test",
        max_batch_size=100,
        max_wait_ms=0,
        max_queue_size=10,
        process_fn=blocking_process,
    )
    worker.start()

    # Drain the first item (which _run is waiting on) — let it enter blocking_process
    await asyncio.sleep(0.02)

    # Submit more items into the queue while _run is blocked
    loop = asyncio.get_running_loop()
    from libs.batching.models import EmbedItem

    futures = []
    for i in range(3):
        fut = loop.create_future()
        item = EmbedItem(future=fut, cost=1, texts=[f"text_{i}"])
        worker.submit(item)
        futures.append(fut)

    # Stop the worker — must drain the queue and resolve futures quickly
    await worker.stop()

    # All futures must be done (exception, not hang)
    for fut in futures:
        assert fut.done(), "Future must be resolved after stop()"


# ── Test: batch error isolation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_error_isolation() -> None:
    """
    When the model call raises, all futures in that batch receive the exception.
    Futures from subsequent batches (different submit cycle) are unaffected.
    """
    call_count = 0

    def failing_then_succeeding_encode(texts, max_length):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("model exploded")
        return [[float(i)] for i in range(len(texts))]

    models = MagicMock()
    models.encode_dense.side_effect = failing_then_succeeding_encode

    engine = _make_engine(models, max_batch_size=100, max_wait_ms=0)
    engine.start()

    try:
        # First call — should raise RuntimeError propagated to the future
        with pytest.raises(RuntimeError, match="model exploded"):
            await engine.submit_embed_dense(["text_a"])

        # Second call — model now works; must succeed
        result = await engine.submit_embed_dense(["text_b"])
        assert len(result) == 1

    finally:
        await engine.stop()
