# ====== Code Summary ======
# BatchingEngine: the submit / touch core. Owns FIVE BatchQueueWorkers (dense / sparse / colbert /
# embed_all / rerank) and TWO asyncio.Locks: embed_lock (dense/sparse/colbert/embed_all, which all
# share BgeModelsService.embed_model) and rerank_lock (independent -- BgeModelsService.reranker is a
# separate FlagReranker instance, so rerank is not serialized behind embed calls). Public submit_*
# coroutines (and embed_all) create a Future, wrap it in the appropriate BatchItem, enqueue it, and
# await the result. The per-kind flatten / model call / scatter logic lives in the BatchProcessor
# subclasses of ``processors/`` (one per worker); each worker's process_fn is its processor's
# ``process`` method.
# Per-item error isolation: batch failures set the exception on every future in the batch.
# embed_all gets cross-request coalescing exactly like dense/sparse/colbert (a dedicated
# BatchQueueWorker + queue), since it is the PRIMARY production path (the DocForge embed node
# hits it first) and previously missed out on batching entirely. The touch_* methods remain the
# only "direct" call shapes: they skip all five BatchQueueWorker queues but still acquire
# embed_lock/rerank_lock, so they stay mutually exclusive with every batched call on the same
# shared model instance.

# ====== Standard Library Imports ======
import asyncio
from typing import TYPE_CHECKING

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .models import EmbedAllItem, EmbedItem, RerankItem
from .processors import (
    BatchProcessor,
    ColbertProcessor,
    DenseProcessor,
    EmbedAllProcessor,
    RerankProcessor,
    SparseProcessor,
)

if TYPE_CHECKING:
    from libs.bge_models.service import BgeModelsService

    from .worker import BatchQueueWorker


class BatchingEngine(LoggerClass):
    """
    Composes five BatchQueueWorkers (dense / sparse / colbert / embed_all / rerank) with two
    model locks.

    Architecture:
    - One worker per op-type so batches form independently per op; each worker's batches are
      processed by the matching BatchProcessor (``processors/``).
    - TWO asyncio.Locks, not one:
        - embed_lock: shared by dense, sparse, colbert, and embed_all, which all call the same
          embed_model (BGEM3FlagModel) instance; concurrent forward passes on shared
          torch/tokenizer/CUDA state are unsafe, so these four are serialised together.
        - rerank_lock: rerank calls a SEPARATE FlagReranker instance (BgeModelsService.reranker),
          so it has no shared-state reason to serialise behind embed calls. Coupling it to
          embed_lock would head-of-line-block interactive search reranking behind bulk
          ingestion embedding, which can legitimately run for seconds. On CPU deployments
          (the default), BgeModelsService derives torch's intra-op thread cap assuming up to
          two concurrent forward passes (embed-family + rerank) -- see
          BgeModelsService._max_concurrency -- to bound thread-pool oversubscription now that
          both locks can be held at once.
    - submit_* coroutines (and embed_all) are the primary public interface: create Future ->
      enqueue item -> await Future. QueueFullError propagates to the caller unchanged when the
      relevant worker's bounded queue is full.
    - touch_* are the only "direct" call shapes left: they bypass all five BatchQueueWorker
      queues (no Future/batch formation) but still acquire embed_lock / rerank_lock, so they
      stay mutually exclusive with every submit_*-driven (or embed_all) batch. Any caller that
      reaches the shared embed_model/reranker MUST go through a queued submit / embed_all call
      or a touch_* method -- never call BgeModelsService directly without holding the matching
      lock.

    Error isolation:
    - BatchProcessor.process wraps the lock+to_thread+scatter in try/except. On any failure,
      the exception is distributed to all futures in the batch so no HTTP request hangs.
    """

    def __init__(
        self,
        models: "BgeModelsService",
        max_length: int,
        max_batch_size: int,
        max_wait_ms: int,
        max_queue_size: int,
        max_concurrent: int = 2,
        sub_batch_size: int = 0,
        small_max_items: int = 0,
    ) -> None:
        """
        Args:
            models (BgeModelsService): Loaded BGE model service. Must have load() called before
                the engine is started.
            max_length (int): Max token length forwarded to encode_dense / encode_sparse /
                encode_colbert. Comes from BGE_M3_MAX_LENGTH config.
            max_batch_size (int): Maximum total cost (units) per batch across all five workers.
            max_wait_ms (int): Batch formation window in milliseconds.
            max_queue_size (int): Per-worker bounded queue capacity.
            max_concurrent (int): Global cap on simultaneous forward passes across embed AND
                rerank (BGE_MAX_CONCURRENT, resolved by BgeModelsService). The per-model locks
                below stay: they keep one model instance single-threaded when the cap is > 1.
            sub_batch_size (int): Texts/pairs per model call inside a formed batch (0 = one call
                for the whole batch). Between calls, work nobody is waiting for is dropped.
            small_max_items (int): Priority-lane threshold forwarded to every worker (0 = off).
        """
        LoggerClass.__init__(self)

        self._models = models
        # Global admission gate: at most max_concurrent forward passes in flight service-wide.
        self._gate = asyncio.Semaphore(max(1, max_concurrent))

        # embed_lock -- dense, sparse, and colbert all call the same embed_model instance, so
        # they share this lock (safety invariant: no concurrent forward passes on one instance).
        self._embed_lock = asyncio.Lock()
        # rerank_lock -- the reranker is a separate FlagReranker instance with no shared state
        # with embed_model, so it gets its own lock instead of queuing behind embed calls.
        self._rerank_lock = asyncio.Lock()

        def worker(name: str, processor: BatchProcessor) -> "BatchQueueWorker":
            # Import here to avoid circular imports at module level; BatchQueueWorker only needs
            # the models attribute at process time, not at construction.
            from .worker import BatchQueueWorker  # noqa: PLC0415

            return BatchQueueWorker(
                name=name,
                max_batch_size=max_batch_size,
                max_wait_ms=max_wait_ms,
                max_queue_size=max_queue_size,
                small_max_items=small_max_items,
                process_fn=processor.process,
            )

        embed_args = (models, self._gate, self._embed_lock, sub_batch_size, max_length)
        self._dense_worker = worker("dense", DenseProcessor(*embed_args))
        self._sparse_worker = worker("sparse", SparseProcessor(*embed_args))
        self._colbert_worker = worker("colbert", ColbertProcessor(*embed_args))
        # embed_all is the PRIMARY production path (the DocForge embed node hits it first) -- it
        # gets its own BatchQueueWorker so concurrent callers coalesce into single model calls
        # exactly like dense/sparse/colbert, instead of the old in-flight-counter admission that
        # only bounded concurrency without ever batching across requests.
        self._embed_all_worker = worker("embed_all", EmbedAllProcessor(*embed_args))
        self._rerank_worker = worker(
            "rerank",
            RerankProcessor(models, self._gate, self._rerank_lock, sub_batch_size),
        )

    # ── Public methods ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start all five background worker tasks.

        Must be called from within the FastAPI lifespan (after the event loop is running).
        """
        self._dense_worker.start()
        self._sparse_worker.start()
        self._colbert_worker.start()
        self._embed_all_worker.start()
        self._rerank_worker.start()
        self.logger.info(
            f"BatchingEngine started "
            f"(max_batch_size={self._dense_worker._max_batch_size}, "
            f"max_wait_ms={self._dense_worker._max_wait_ms}, "
            f"max_queue_size={self._dense_worker._queue.maxsize})"
        )

    async def stop(self) -> None:
        """
        Stop all five workers in order, draining pending futures before model unload.

        Shutdown order: dense -> sparse -> colbert -> embed_all -> rerank. Each stop() drains
        its queue and resolves all pending futures with QueueFullError so no client request
        hangs indefinitely.
        """
        self.logger.info(f"BatchingEngine stopping...")
        await self._dense_worker.stop()
        await self._sparse_worker.stop()
        await self._colbert_worker.stop()
        await self._embed_all_worker.stop()
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

        # 3. Await the future; result set by DenseProcessor scatter
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
        self, texts: list[str]
    ) -> tuple[list[list[float]], list[list[dict[str, int | float]]]]:
        """
        Encode both dense and sparse vectors for ``texts`` in ONE shared model forward pass.

        Submitted to the dedicated embed_all BatchQueueWorker, exactly like
        ``submit_embed_dense``/``submit_embed_sparse``/``submit_embed_colbert``: concurrent
        callers are coalesced into a single ``encode_dense_sparse`` call (cross-request
        batching), not just admitted under a shared lock one at a time. This is the PRIMARY
        production path (the DocForge embed node hits it first), so coalescing here matters as
        much as it does for /embed. The model call still runs under ``embed_lock`` — the SAME
        lock the dense/sparse/colbert workers hold — so a formed embed_all batch can never
        overlap a dense or sparse batch on the shared ``embed_model`` instance. Uses the
        engine's configured ``max_length`` (the same value the dense/sparse workers use), so
        results are identical to calling the two separate paths with that same config.

        Args:
            texts (list[str]): Texts to embed. Must be non-empty (caller's responsibility).

        Returns:
            tuple[list[list[float]], list[list[dict]]]: A ``(dense, sparse)`` pair whose two
                sub-shapes are identical to submitting the same texts to the dense and sparse
                paths separately.

        Raises:
            QueueFullError: When the embed_all worker's bounded queue is at capacity.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[list[list[float]], list[list[dict[str, int | float]]]]] = (
            loop.create_future()
        )
        item = EmbedAllItem(future=future, cost=len(texts), texts=texts)
        self._embed_all_worker.submit(item)
        return await future

    async def touch_dense(self, max_length: int) -> None:
        """
        Run a single-item dense forward pass under embed_lock, bypassing the batch queues.

        Exists for keep-warm callers: a tiny forward pass on the shared embed_model that still
        acquires the SAME embed_lock a real dense/sparse/colbert batch (or embed_all) would
        hold, so it can never run concurrently with one of them on the shared torch/tokenizer
        state — that overlap is exactly the thread-safety hazard embed_lock exists to prevent.
        Skips all five BatchQueueWorker queues entirely, so it never competes for queue
        CAPACITY with real traffic (only for the lock, like any other caller).

        Args:
            max_length (int): Tokenizer max length forwarded to encode_dense.
        """
        async with self._gate, self._embed_lock:
            await asyncio.to_thread(self._models.encode_dense, ["warm"], max_length)

    async def touch_sparse(self, max_length: int) -> None:
        """
        Run a single-item sparse forward pass under embed_lock, bypassing the batch queues.

        See touch_dense for the full locking rationale — sparse shares the same embed_model
        instance as dense/colbert, so it is guarded by the same embed_lock.

        Args:
            max_length (int): Tokenizer max length forwarded to encode_sparse.
        """
        async with self._gate, self._embed_lock:
            await asyncio.to_thread(self._models.encode_sparse, ["warm"], max_length)

    async def touch_rerank(self) -> None:
        """
        Run a single-pair rerank forward pass under rerank_lock, bypassing the batch queue.

        See touch_dense for the locking rationale; rerank uses its own independent
        rerank_lock/FlagReranker instance, so it is guarded separately from embed_lock.
        """
        async with self._gate, self._rerank_lock:
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
