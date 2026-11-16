# ====== Code Summary ======
# KeepWarm: background task that periodically touches every model so its weights stay resident.
# On a memory-constrained host an idle process's ~GB working set is paged out, so the next real
# request pays a 30-50 s page-in ("cold load") that stalls the rerank worker and cascades into
# timeouts. A cheap periodic touch keeps the weights resident. Disabled with BGE_KEEPWARM_SECONDS=0.

# ====== Standard Library Imports ======
import asyncio

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from libs.batching import BatchingEngine


class KeepWarm(LoggerClass):
    """
    Periodically touches every model through the batching engine.

    The engine's ``touch_dense``/``touch_sparse``/``touch_rerank`` methods acquire the SAME
    embed_lock/rerank_lock a real dense/sparse/colbert/rerank batch would hold, so a keep-warm tick
    can NEVER run concurrently with real traffic on the shared embed_model / reranker instances --
    calling the model service directly (bypassing the engine's locks) would let a keep-warm
    forward pass race a real batch on that shared, thread-unsafe torch/tokenizer state. They still
    bypass all five BatchQueueWorker queues, so a tick never competes for queue CAPACITY with real
    traffic. touch_rerank is skipped when the reranker was never loaded (BGE_LOAD_RERANKER=false).
    Each tick is best-effort so a transient failure only skips one round.

    Args:
        engine (BatchingEngine): The started batching engine.
        reranker_loaded (bool): Whether the reranker exists (nothing to keep warm otherwise).
        interval_seconds (int): Seconds between keep-warm rounds (caller guarantees > 0).
        max_length (int): The tokenizer max length used for the dummy embed passes.
    """

    def __init__(
        self,
        engine: BatchingEngine,
        reranker_loaded: bool,
        interval_seconds: int,
        max_length: int,
    ) -> None:
        LoggerClass.__init__(self)
        self._engine = engine
        self._reranker_loaded = reranker_loaded
        self._interval_seconds = interval_seconds
        self._max_length = max_length
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Create the background task on the running event loop."""
        self._task = asyncio.create_task(self._run())
        self.logger.info(f"Keep-warm every {self._interval_seconds}s enabled")

    async def stop(self) -> None:
        """Cancel the task and wait for it (no-op when it was never started)."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _run(self) -> None:
        """Touch every model each interval until cancelled at shutdown."""
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                await self._engine.touch_dense(self._max_length)
                await self._engine.touch_sparse(self._max_length)
                if self._reranker_loaded:
                    await self._engine.touch_rerank()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — a keep-warm miss must never crash the task
                self.logger.warning(f"Keep-warm round failed (non-fatal): {exc}")
