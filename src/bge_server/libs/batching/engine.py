# ====== Code Summary ======
# BatchingEngine: owns four BatchQueueWorkers (dense / sparse / colbert / rerank) and TWO
# asyncio.Locks: embed_lock (dense/sparse/colbert, which share BgeModelsService.embed_model) and
# rerank_lock (independent — BgeModelsService.reranker is a separate FlagReranker instance, so
# rerank is not serialized behind embed calls). Public submit_* coroutines create a Future, wrap
# it in the appropriate BatchItem, enqueue it, and await the result. Protected _process_* methods
# flatten the batch, run the model call under the relevant lock via asyncio.to_thread, and scatter
# results back to each item's future. Rerank scatter re-numbers indices 0..n-1 per request and
# sorts results score-descending to match TEI's /rerank response order.
# Per-item error isolation: batch failures set the exception on every future in the batch.
# embed_all and the touch_* methods are the "direct" call shapes: they skip the four
# BatchQueueWorker queues entirely but still acquire embed_lock/rerank_lock, so they remain
# mutually exclusive with every batched call on the same shared model instance. embed_all has no
# per-op queue of its own, so it enforces its OWN bounded admission (an in-flight counter capped
# at max_queue_size) and raises QueueFullError past that cap -- the same back-pressure contract
# the four queued paths give the router, just enforced differently since there is no queue to fill.

# ====== Standard Library Imports ======
import asyncio
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .models import BatchItem, EmbedItem, QueueFullError, RerankItem

if TYPE_CHECKING:
    from libs.bge_models.service import BgeModelsService


class BatchingEngine(LoggerClass):
    """
    Composes four BatchQueueWorkers (dense / sparse / colbert / rerank) with two model locks.

    Architecture:
    - One worker per op-type so batches form independently per op.
    - TWO asyncio.Locks, not one:
        - embed_lock: shared by dense, sparse, and colbert, which all call the same
          embed_model (BGEM3FlagModel) instance; concurrent forward passes on shared
          torch/tokenizer/CUDA state are unsafe, so these three are serialised together.
        - rerank_lock: rerank calls a SEPARATE FlagReranker instance (BgeModelsService.reranker),
          so it has no shared-state reason to serialise behind embed calls. Coupling it to
          embed_lock would head-of-line-block interactive search reranking behind bulk
          ingestion embedding, which can legitimately run for seconds. On CPU deployments
          (the default), BgeModelsService derives torch's intra-op thread cap assuming up to
          two concurrent forward passes (embed-family + rerank) — see
          BgeModelsService._max_concurrency — to bound thread-pool oversubscription now that
          both locks can be held at once.
    - submit_* coroutines are the primary public interface: create Future -> enqueue item ->
      await Future. QueueFullError propagates to the caller unchanged.
    - embed_all and touch_* are the "direct" call shapes: they bypass the four
      BatchQueueWorker queues (no Future/batch formation) but still acquire embed_lock /
      rerank_lock, so they stay mutually exclusive with every submit_*-driven batch. Any
      caller that reaches the shared embed_model/reranker MUST go through one of these two
      shapes — never call BgeModelsService directly without holding the matching lock.
      embed_all additionally enforces its own bounded admission (see embed_all's docstring)
      since it has no BatchQueueWorker queue to provide that back-pressure for it.

    Error isolation:
    - _process_* methods wrap the lock+to_thread+scatter in try/except. On any failure,
      the exception is distributed to all futures in the batch so no HTTP request hangs.
    """

    def __init__(
        self,
        models: "BgeModelsService",
        max_length: int,
        max_batch_size: int,
        max_wait_ms: int,
        max_queue_size: int,
    ) -> None:
        """
        Args:
            models (BgeModelsService): Loaded BGE model service. Must have load() called before
                the engine is started.
            max_length (int): Max token length forwarded to encode_dense / encode_sparse /
                encode_colbert. Comes from BGE_M3_MAX_LENGTH config.
            max_batch_size (int): Maximum total cost (units) per batch across all four workers.
            max_wait_ms (int): Batch formation window in milliseconds.
            max_queue_size (int): Per-worker bounded queue capacity.
        """
        LoggerClass.__init__(self)

        self._models = models
        self._max_length = max_length

        # embed_lock — dense, sparse, and colbert all call the same embed_model instance, so
        # they share this lock (safety invariant: no concurrent forward passes on one instance).
        self._embed_lock = asyncio.Lock()
        # rerank_lock — the reranker is a separate FlagReranker instance with no shared state
        # with embed_model, so it gets its own lock instead of queuing behind embed calls.
        self._rerank_lock = asyncio.Lock()

        # embed_all bypasses the four BatchQueueWorker queues entirely (see embed_all's
        # docstring), so it has no bounded queue to reject excess callers with. This in-flight
        # counter reproduces that same back-pressure contract: once max_queue_size embed_all
        # calls are already admitted (waiting on embed_lock or running the forward pass), any
        # further call is rejected immediately with QueueFullError instead of piling up
        # unboundedly behind the lock — the same admission ceiling the queued paths get for free.
        self._embed_all_max_inflight = max_queue_size
        self._embed_all_inflight = 0

        # Import here to avoid circular imports at module level; BatchQueueWorker only needs
        # the models attribute at process time, not at construction.
        from .worker import BatchQueueWorker  # noqa: PLC0415

        self._dense_worker = BatchQueueWorker(
            name="dense",
            max_batch_size=max_batch_size,
            max_wait_ms=max_wait_ms,
            max_queue_size=max_queue_size,
            process_fn=self._process_dense,
        )
        self._sparse_worker = BatchQueueWorker(
            name="sparse",
            max_batch_size=max_batch_size,
            max_wait_ms=max_wait_ms,
            max_queue_size=max_queue_size,
            process_fn=self._process_sparse,
        )
        self._colbert_worker = BatchQueueWorker(
            name="colbert",
            max_batch_size=max_batch_size,
            max_wait_ms=max_wait_ms,
            max_queue_size=max_queue_size,
            process_fn=self._process_colbert,
        )
        self._rerank_worker = BatchQueueWorker(
            name="rerank",
            max_batch_size=max_batch_size,
            max_wait_ms=max_wait_ms,
            max_queue_size=max_queue_size,
            process_fn=self._process_rerank,
        )

    # ── Protected process methods ──────────────────────────────────────────────

    async def _process_dense(self, batch: list[BatchItem]) -> None:
        """
        Flatten, run dense encode under the model lock, scatter results back.

        Args:
            batch (list[BatchItem]): Batch of EmbedItem instances from the dense worker.
        """
        # Cast for type safety — the dense worker only receives EmbedItem
        items: list[EmbedItem] = [i for i in batch if isinstance(i, EmbedItem)]
        try:
            # 1. Flatten all texts and record per-item offsets for scatter
            flat_texts: list[str] = []
            offsets: list[tuple[int, int]] = []
            for item in items:
                start = len(flat_texts)
                flat_texts.extend(item.texts)
                offsets.append((start, len(flat_texts)))

            # 2. Run the model call in a thread to avoid blocking the event loop;
            #    acquire embed_lock first so dense/sparse/colbert calls never overlap.
            max_length = self._max_length
            async with self._embed_lock:
                vecs: list[list[float]] = await asyncio.to_thread(
                    self._models.encode_dense, flat_texts, max_length
                )

            # 3. Scatter results back to each item's future by text slice
            for item, (start, end) in zip(items, offsets):
                if not item.future.done():
                    item.future.set_result(vecs[start:end])

        except Exception as exc:
            # Error isolation: distribute failure to every future so no request hangs
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)

    async def _process_sparse(self, batch: list[BatchItem]) -> None:
        """
        Flatten, run sparse encode under embed_lock, scatter results back.

        Args:
            batch (list[BatchItem]): Batch of EmbedItem instances from the sparse worker.
        """
        items: list[EmbedItem] = [i for i in batch if isinstance(i, EmbedItem)]
        try:
            # 1. Flatten texts + record offsets
            flat_texts: list[str] = []
            offsets: list[tuple[int, int]] = []
            for item in items:
                start = len(flat_texts)
                flat_texts.extend(item.texts)
                offsets.append((start, len(flat_texts)))

            # 2. embed_lock + to_thread (same embed_model as dense — mandatory serialisation)
            max_length = self._max_length
            async with self._embed_lock:
                token_lists: list[list[dict]] = await asyncio.to_thread(
                    self._models.encode_sparse, flat_texts, max_length
                )

            # 3. Scatter by offsets
            for item, (start, end) in zip(items, offsets):
                if not item.future.done():
                    item.future.set_result(token_lists[start:end])

        except Exception as exc:
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)

    async def _process_colbert(self, batch: list[BatchItem]) -> None:
        """
        Flatten, run colbert encode under embed_lock, scatter results back.

        Args:
            batch (list[BatchItem]): Batch of EmbedItem instances from the colbert worker.
        """
        items: list[EmbedItem] = [i for i in batch if isinstance(i, EmbedItem)]
        try:
            # 1. Flatten texts + record offsets
            flat_texts: list[str] = []
            offsets: list[tuple[int, int]] = []
            for item in items:
                start = len(flat_texts)
                flat_texts.extend(item.texts)
                offsets.append((start, len(flat_texts)))

            # 2. embed_lock + to_thread (same embed_model as dense/sparse — mandatory serialisation)
            max_length = self._max_length
            async with self._embed_lock:
                token_vec_lists: list[list[list[float]]] = await asyncio.to_thread(
                    self._models.encode_colbert, flat_texts, max_length
                )

            # 3. Scatter by offsets
            for item, (start, end) in zip(items, offsets):
                if not item.future.done():
                    item.future.set_result(token_vec_lists[start:end])

        except Exception as exc:
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)

    async def _process_rerank(self, batch: list[BatchItem]) -> None:
        """
        Flatten all (query, text) pairs, score in one model call, scatter per-request results.

        Each request's results are re-indexed 0..n-1 (not global offsets) so the TEI contract
        is honoured: the DocForge bge_reranker provider expects local indices. Results are also
        sorted score-descending per request, matching TEI's own /rerank response order (the
        DocForge client maps scores back onto candidates by ``index`` and does not depend on
        response order, so this ordering is purely a TEI-parity concern, not a correctness one).

        Args:
            batch (list[BatchItem]): Batch of RerankItem instances from the rerank worker.
        """
        items: list[RerankItem] = [i for i in batch if isinstance(i, RerankItem)]
        try:
            # 1. Build flat list of [query, text] pairs + record per-request sizes for scatter
            flat_pairs: list[list[str]] = []
            sizes: list[int] = []
            for item in items:
                for text in item.texts:
                    flat_pairs.append([item.query, text])
                sizes.append(len(item.texts))

            # 2. One model call for the entire cross-batch under rerank_lock (independent from
            #    embed_lock — the reranker is a separate FlagReranker instance, so a large
            #    embed batch never blocks an interactive rerank call, and vice versa)
            async with self._rerank_lock:
                flat_scores: list[float] = await asyncio.to_thread(
                    self._models.compute_rerank_scores_flat, flat_pairs
                )

            # 3. Scatter scores back; re-number indices 0..n-1 per request (not global), then
            #    sort score-descending to match TEI's own /rerank response order.
            offset = 0
            for item, size in zip(items, sizes):
                scores = flat_scores[offset : offset + size]
                result = sorted(
                    ({"index": i, "score": float(s)} for i, s in enumerate(scores)),
                    key=lambda r: r["score"],
                    reverse=True,
                )
                if not item.future.done():
                    item.future.set_result(result)
                offset += size

        except Exception as exc:
            for item in items:
                if not item.future.done():
                    item.future.set_exception(exc)

    # ── Public methods ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start all four background worker tasks.

        Must be called from within the FastAPI lifespan (after the event loop is running).
        """
        self._dense_worker.start()
        self._sparse_worker.start()
        self._colbert_worker.start()
        self._rerank_worker.start()
        self.logger.info(
            f"BatchingEngine started "
            f"(max_batch_size={self._dense_worker._max_batch_size}, "
            f"max_wait_ms={self._dense_worker._max_wait_ms}, "
            f"max_queue_size={self._dense_worker._queue.maxsize})"
        )

    async def stop(self) -> None:
        """
        Stop all four workers in order, draining pending futures before model unload.

        Shutdown order: dense -> sparse -> colbert -> rerank. Each stop() drains its queue
        and resolves all pending futures with QueueFullError so no client request hangs
        indefinitely.
        """
        self.logger.info(f"BatchingEngine stopping...")
        await self._dense_worker.stop()
        await self._sparse_worker.stop()
        await self._colbert_worker.stop()
        await self._rerank_worker.stop()
        self.logger.info(f"BatchingEngine stopped")

    async def submit_embed_dense(self, texts: list[str]) -> list[list[float]]:
        """
        Submit a dense embedding request and await its result.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty (caller's responsibility).

        Returns:
            list[list[float]]: One 1024-dim dense vector per input text.

        Raises:
            QueueFullError: When the dense worker queue is at capacity.
        """
        # 1. Create the future in the running event loop
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[list[float]]] = loop.create_future()

        # 2. Wrap in an EmbedItem and enqueue — cost = number of texts
        item = EmbedItem(future=future, cost=len(texts), texts=texts)
        self._dense_worker.submit(item)

        # 3. Await the future; result set by _process_dense scatter
        return await future

    async def submit_embed_sparse(self, texts: list[str]) -> list[list[dict[str, int | float]]]:
        """
        Submit a sparse embedding request and await its result.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty (caller's responsibility).

        Returns:
            list[list[dict]]: Per text, a list of {"index": int, "value": float} token dicts.

        Raises:
            QueueFullError: When the sparse worker queue is at capacity.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[list[dict[str, int | float]]]] = loop.create_future()
        item = EmbedItem(future=future, cost=len(texts), texts=texts)
        self._sparse_worker.submit(item)
        return await future

    async def submit_embed_colbert(self, texts: list[str]) -> list[list[list[float]]]:
        """
        Submit a ColBERT multi-vector embedding request and await its result.

        Not part of the TEI contract — an internal DocForge convention (BGE-M3's native
        colbert head, shares the same embed_model instance as dense/sparse).

        Args:
            texts (list[str]): Texts to embed. Must be non-empty (caller's responsibility).

        Returns:
            list[list[list[float]]]: Per input text, a list of per-token 1024-dim vectors
                (variable length per text).

        Raises:
            QueueFullError: When the colbert worker queue is at capacity.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[list[list[float]]]] = loop.create_future()
        item = EmbedItem(future=future, cost=len(texts), texts=texts)
        self._colbert_worker.submit(item)
        return await future

    async def embed_all(
        self, texts: list[str], max_length: int
    ) -> tuple[list[list[float]], list[list[dict[str, int | float]]]]:
        """
        Encode both dense and sparse vectors for ``texts`` in ONE shared model forward pass.

        Unlike the dense/sparse/colbert workers, this path is NOT batched across concurrent
        requests: it calls the model directly. It is still serialised on ``embed_lock`` — the
        SAME lock the dense/sparse/colbert workers hold — so the combined forward pass can never
        overlap a dense or sparse batch on the shared ``embed_model`` instance. The model call is
        offloaded with ``asyncio.to_thread`` exactly like ``_process_dense``, keeping the event
        loop free during the (seconds-long) forward pass.

        Back-pressure: this path has no BatchQueueWorker queue, so admission is bounded by an
        in-flight counter instead — capped at the same ``max_queue_size`` the four queued paths
        use. Once that many embed_all calls are already admitted (queued on embed_lock or mid
        forward-pass), further calls raise QueueFullError immediately rather than accumulating
        unboundedly while every caller waits its turn on embed_lock. This mirrors, rather than
        skips, the back-pressure contract the queued paths give the router for free.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty (caller's responsibility).
            max_length (int): Maximum token length for truncation.

        Returns:
            tuple[list[list[float]], list[list[dict]]]: A ``(dense, sparse)`` pair whose two
                sub-shapes are identical to submitting the same texts to the dense and sparse
                paths separately.

        Raises:
            QueueFullError: When ``max_queue_size`` embed_all calls are already admitted.
        """
        if self._embed_all_inflight >= self._embed_all_max_inflight:
            raise QueueFullError(
                f"[embed_all] {self._embed_all_max_inflight} requests already in flight — "
                f"server overloaded"
            )
        self._embed_all_inflight += 1
        try:
            async with self._embed_lock:
                return await asyncio.to_thread(self._models.encode_dense_sparse, texts, max_length)
        finally:
            self._embed_all_inflight -= 1

    async def touch_dense(self, max_length: int) -> None:
        """
        Run a single-item dense forward pass under embed_lock, bypassing the batch queues.

        Exists for keep-warm callers: a tiny forward pass on the shared embed_model that still
        acquires the SAME embed_lock a real dense/sparse/colbert batch (or embed_all) would
        hold, so it can never run concurrently with one of them on the shared torch/tokenizer
        state — that overlap is exactly the thread-safety hazard embed_lock exists to prevent.
        Skips the four BatchQueueWorker queues entirely, so it never competes for queue
        CAPACITY with real traffic (only for the lock, like any other caller).

        Args:
            max_length (int): Tokenizer max length forwarded to encode_dense.
        """
        async with self._embed_lock:
            await asyncio.to_thread(self._models.encode_dense, ["warm"], max_length)

    async def touch_sparse(self, max_length: int) -> None:
        """
        Run a single-item sparse forward pass under embed_lock, bypassing the batch queues.

        See touch_dense for the full locking rationale — sparse shares the same embed_model
        instance as dense/colbert, so it is guarded by the same embed_lock.

        Args:
            max_length (int): Tokenizer max length forwarded to encode_sparse.
        """
        async with self._embed_lock:
            await asyncio.to_thread(self._models.encode_sparse, ["warm"], max_length)

    async def touch_rerank(self) -> None:
        """
        Run a single-pair rerank forward pass under rerank_lock, bypassing the batch queue.

        See touch_dense for the locking rationale; rerank uses its own independent
        rerank_lock/FlagReranker instance, so it is guarded separately from embed_lock.
        """
        async with self._rerank_lock:
            await asyncio.to_thread(self._models.compute_rerank_scores_flat, [["warm", "warm"]])

    async def submit_rerank(self, query: str, texts: list[str]) -> list[dict[str, int | float]]:
        """
        Submit a rerank request and await its result.

        Args:
            query (str): The search query for the cross-encoder.
            texts (list[str]): Candidate texts to score. Must be non-empty.

        Returns:
            list[dict]: One {"index": i, "score": float} per candidate, indices 0..n-1.

        Raises:
            QueueFullError: When the rerank worker queue is at capacity.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[list[dict[str, int | float]]] = loop.create_future()
        item = RerankItem(future=future, cost=len(texts), query=query, texts=texts)
        self._rerank_worker.submit(item)
        return await future
