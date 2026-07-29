# ====== Code Summary ======
# BatchQueueWorker: one generic micro-batcher per inference operation (dense / sparse / rerank).
# A bounded asyncio.Queue receives items from submit(); the _run() loop drains them into a batch
# either when the batch budget (sum of item costs) reaches max_batch_size or when max_wait_ms
# elapses. The formed batch is handed to the injected process_fn for flattening, model inference,
# and result scatter. Error isolation: process_fn exceptions never escape _run(); they are
# distributed to every future in the affected batch via set_exception().

# ====== Standard Library Imports ======
import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .models import BatchItem, QueueFullError


class BatchQueueWorker(LoggerClass):
    """
    Generic micro-batcher for one inference operation (dense / sparse / rerank).

    One worker is created per operation type. The worker runs a single asyncio background
    task (_run) that forms batches from the queue and calls the injected process_fn. Each
    submitted item carries a cost; batches accumulate until the cost budget is met or the
    wait window elapses.

    Concurrency note: the model_lock passed at construction is shared across all three workers.
    Dense and sparse both use the same embed_model instance; concurrent forward passes on shared
    torch state are unsafe. The lock serialises all model calls at the engine level regardless
    of which worker initiates them.
    """

    def __init__(
        self,
        name: str,
        max_batch_size: int,
        max_wait_ms: int,
        max_queue_size: int,
        process_fn: Callable[[list[BatchItem]], Awaitable[None]],
    ) -> None:
        """
        Args:
            name (str): Short label for this worker ("dense", "sparse", "rerank").
                Used in log messages and as part of the logger identifier.
            max_batch_size (int): Maximum total cost (units) per batch. A single item
                whose cost exceeds this value is still admitted whole and processed as
                a batch of one — FlagEmbedding handles its own internal chunking.
            max_wait_ms (int): Maximum time in milliseconds to wait for additional items
                after the first item arrives. 0 means process immediately with whatever
                is available (effectively disables batching beyond the first item).
            max_queue_size (int): Bounded queue capacity. When full, submit() raises
                QueueFullError (translated to HTTP 503 by the router).
            process_fn (Callable): Async function that receives the formed batch and
                performs flatten -> model call -> scatter. Called from within _run().
        """
        LoggerClass.__init__(self)
        self._name = name
        self._max_batch_size = max_batch_size
        self._max_wait_ms = max_wait_ms
        self._queue: asyncio.Queue[BatchItem] = asyncio.Queue(maxsize=max_queue_size)
        self._process_fn = process_fn
        self._task: asyncio.Task[Any] | None = None

    # ── Protected methods ──────────────────────────────────────────────────────

    async def _run(self) -> None:
        """
        Main batch-formation loop. Runs as a background asyncio task until cancelled.

        Waits for the first item, then greedily accumulates additional items until the
        batch budget (sum of costs) reaches max_batch_size or the wait window expires.
        On each formed batch, calls process_fn and catches any exception, distributing
        it to every future in the batch so no awaiting request hangs.
        """
        while True:
            try:
                # 1. Block until the first item arrives — this parks the task cheaply
                first_item = await self._queue.get()
            except asyncio.CancelledError:
                # Task was cancelled by stop() — exit cleanly
                return

            batch: list[BatchItem] = [first_item]
            total_cost = first_item.cost
            t_start = time.perf_counter()

            # 2. Greedily pull more items until budget is met or wait window expires
            if self._max_wait_ms > 0:
                deadline_s = self._max_wait_ms / 1000.0
                while total_cost < self._max_batch_size:
                    elapsed = time.perf_counter() - t_start
                    remaining = deadline_s - elapsed
                    if remaining <= 0:
                        break
                    try:
                        item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                        batch.append(item)
                        total_cost += item.cost
                    except TimeoutError:
                        break
                    except asyncio.CancelledError:
                        # Propagate cancel but first ensure pending futures are resolved
                        self._cancel_batch(batch)
                        return

            waited_ms = int((time.perf_counter() - t_start) * 1000)
            self.logger.debug(
                f"[{self._name}] batch: {len(batch)} reqs, {total_cost} units, waited {waited_ms}ms"
            )

            # 3. Dispatch the formed batch to the process function; isolate errors per-batch
            try:
                await self._process_fn(batch)
            except Exception as exc:
                # Distribute the exception to every future so no client request hangs forever.
                # process_fn normally handles its own errors, so reaching here means an unexpected
                # crash in batch dispatch — log it loudly (with traceback) instead of swallowing.
                self.logger.exception(
                    f"[{self._name}] batch dispatch crashed ({len(batch)} reqs): {exc}"
                )
                for item in batch:
                    if not item.future.done():
                        item.future.set_exception(exc)

    def _cancel_batch(self, batch: list[BatchItem]) -> None:
        """
        Set a CancelledError on every unresolved future in a batch.

        Called when the worker task is cancelled mid-wait so that no client request hangs.

        Args:
            batch (list[BatchItem]): Batch being assembled at the moment of cancellation.
        """
        exc = asyncio.CancelledError("Worker stopped during batch formation")
        for item in batch:
            if not item.future.done():
                item.future.set_exception(exc)

    # ── Public methods ─────────────────────────────────────────────────────────

    def submit(self, item: BatchItem) -> None:
        """
        Enqueue an item for batched processing.

        Uses put_nowait so the caller (engine submit coroutine) can detect back-pressure
        synchronously and raise QueueFullError before awaiting the future.

        Args:
            item (BatchItem): The item to enqueue. Its future must already be created.

        Raises:
            QueueFullError: When the bounded queue is at capacity.
        """
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            raise QueueFullError(
                f"[{self._name}] queue full ({self._queue.maxsize} items) — server overloaded"
            )

    def start(self) -> None:
        """
        Start the background batch-formation task.

        Must be called after the asyncio event loop is running (i.e. from within the
        FastAPI lifespan). Creates a single asyncio.Task that runs _run() until stop()
        is called.
        """
        self._task = asyncio.create_task(self._run(), name=f"bge-batch-{self._name}")
        self.logger.info(f"[{self._name}] BatchQueueWorker started")

    async def stop(self) -> None:
        """
        Stop the background task and drain any pending items from the queue.

        Cancels the running task, then iterates the queue setting QueueFullError on every
        remaining item's future so that no awaiting HTTP handler hangs indefinitely.
        Should be called before the model service is unloaded.
        """
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected — we just cancelled it
            except Exception as exc:
                # The task should exit cleanly on cancel; an unexpected error here must be visible.
                self.logger.warning(f"[{self._name}] worker task raised during shutdown: {exc}")

        # Drain any items still sitting in the queue after task cancellation
        drained = 0
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if not item.future.done():
                    item.future.set_exception(
                        QueueFullError(f"[{self._name}] worker stopped — request cancelled")
                    )
                drained += 1
            except asyncio.QueueEmpty:
                break

        self.logger.info(f"[{self._name}] BatchQueueWorker stopped (drained {drained} pending items)")
