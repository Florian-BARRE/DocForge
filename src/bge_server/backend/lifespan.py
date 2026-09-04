# ====== Code Summary ======
# Provides the FastAPI lifespan context manager: loads BGE models at startup, builds and starts
# the dynamic-batching engine, runs a best-effort warmup forward pass, logs the banner and config,
# and shuts everything down cleanly on exit. Uses hasattr guards in the finally block so a partial
# startup never raises during teardown. Shutdown order: batching engine stop (drains pending
# futures) THEN model unload (frees GPU/CPU memory) — guarantees no scatter operation touches an
# unloaded model.

# ====== Standard Library Imports ======
import asyncio
import unicodedata
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pyfiglet import Figlet

# ====== Internal Project Imports ======
from libs.batching import BatchingEngine

# ====== Local Project Imports ======
from .context import CONTEXT

# Number of discrete startup steps — update when adding or removing steps.
TOTAL_STEPS = 4

logger = loggerplusplus.bind(identifier="BGEServer")


async def _keep_warm(interval_seconds: int, max_length: int) -> None:
    """
    Periodically touch every model so its weights stay resident (never paged out).

    Runs a tiny forward pass per inference path every ``interval_seconds``, through the
    batching engine's ``touch_dense``/``touch_sparse``/``touch_rerank`` methods. Those acquire
    the SAME embed_lock/rerank_lock a real dense/sparse/colbert/rerank batch would hold, so a
    keep-warm tick can NEVER run concurrently with real traffic on the shared embed_model /
    reranker instances — calling the model service directly (bypassing both the engine's
    queues AND its locks) would let a keep-warm tick's forward pass race a real batch's forward
    pass on that shared torch/tokenizer state, which is thread-unsafe. The engine methods still
    bypass the four BatchQueueWorker queues, so a keep-warm tick never competes for queue
    CAPACITY with real traffic — only for the lock, exactly like any other caller. Each tick is
    best-effort so a transient failure only skips one round. Cancelled at shutdown.

    Args:
        interval_seconds (int): Seconds between keep-warm rounds (caller guarantees > 0).
        max_length (int): The tokenizer max length used for the dummy embed passes.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            engine = CONTEXT.batching_engine
            await engine.touch_dense(max_length)
            await engine.touch_sparse(max_length)
            await engine.touch_rerank()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — a keep-warm miss must never crash the task
            logger.warning(f"Keep-warm round failed (non-fatal): {exc}")


def lifespan() -> Any:
    """
    Return the FastAPI lifespan context manager factory.

    Returns:
        Any: Async context manager suitable for FastAPI's ``lifespan`` parameter.
    """

    def _log_step(step: int, message: str) -> None:
        """Log a numbered startup step to make progress visible in the container logs."""
        logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}...")

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        """
        Manage FastAPI startup and shutdown.

        Yields:
            None: Yields control to FastAPI while the service is running.
        """
        _ = app
        keep_warm_task: asyncio.Task[None] | None = None
        try:
            # 1. Print startup banner (strip accents for ASCII console safety)
            app_name = "BGE Server"
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c
                    for c in unicodedata.normalize("NFD", app_name)
                    if unicodedata.category(c) != "Mn"
                )
            )
            logger.info(f"{banner}")

            # 2. Log runtime configuration so env-overrides are visible at boot, then
            # validate fail-fast BEFORE the slow model load — invalid config must abort
            # startup immediately, not after downloading ~4.4 GiB of weights.
            _log_step(1, "Runtime configuration")
            logger.info(f"{CONTEXT.CONFIG}")
            CONTEXT.CONFIG.validate()

            # 3. Load BGE models — the slow step (~30-120 s on first run, weights download).
            # Must complete before the batching engine is started so that _process_* methods
            # can safely call the model service.
            _log_step(2, "Loading BGE models")
            CONTEXT.bge_models.load()

            # 4. Build and start the dynamic-batching engine.
            # The engine owns three per-op workers (dense / sparse / rerank) plus a single
            # shared asyncio.Lock that serialises all model calls across workers. Workers
            # are started here (creates asyncio tasks) — must be inside the lifespan so the
            # tasks bind to the correct asyncio event loop (hot-reload safety).
            _log_step(3, "Starting batching engine")
            CONTEXT.batching_engine = BatchingEngine(
                models=CONTEXT.bge_models,
                max_length=CONTEXT.CONFIG.BGE_M3_MAX_LENGTH,
                max_batch_size=CONTEXT.CONFIG.BGE_MAX_BATCH_SIZE,
                max_wait_ms=CONTEXT.CONFIG.BGE_MAX_WAIT_MS,
                max_queue_size=CONTEXT.CONFIG.BGE_MAX_QUEUE_SIZE,
            )
            CONTEXT.batching_engine.start()

            # 5. Warmup — one tiny dummy forward pass per inference path (dense/sparse/colbert/rerank)
            # so the first REAL request doesn't pay lazy CUDA-kernel-compile / allocator costs. Calls
            # the model service DIRECTLY (not through the batching engine/HTTP) — the engine isn't
            # needed to prime the model, and going through it would just add queue/lock overhead.
            # colbert is primed too: it has its OWN route (/embed_colbert) and its own forward pass
            # (the colbert head), so an unwarmed colbert path would leave the first late-interaction
            # request cold. Best-effort: a warmup failure must never abort startup, only slow the
            # first request.
            _log_step(4, "Warmup pass")
            try:
                max_length = CONTEXT.CONFIG.BGE_M3_MAX_LENGTH
                CONTEXT.bge_models.encode_dense(["warmup"], max_length=max_length)
                CONTEXT.bge_models.encode_sparse(["warmup"], max_length=max_length)
                # Prime the combined dense+sparse path too (its own encode() call shape) so the
                # first real /embed_all request doesn't pay lazy kernel-compile / allocator costs.
                CONTEXT.bge_models.encode_dense_sparse(["warmup"], max_length=max_length)
                CONTEXT.bge_models.encode_colbert(["warmup"], max_length=max_length)
                CONTEXT.bge_models.compute_rerank_scores_flat([["warmup", "warmup"]])
                logger.info(f"Warmup pass completed")
            except Exception as exc:  # noqa: BLE001 — a warmup miss must never crash the lifespan
                logger.warning(f"Warmup pass failed (non-fatal, continuing startup): {exc}")

            # 5b. Keep-warm — on a memory-constrained host an idle process's ~GB working set is
            # paged out, so the next real request pays a 30-50 s page-in ("cold load") that stalls
            # the rerank worker and cascades into timeouts. A cheap periodic touch keeps the weights
            # resident. Disabled with BGE_KEEPWARM_SECONDS=0 (e.g. on a GPU box that never pages out).
            if CONTEXT.CONFIG.BGE_KEEPWARM_SECONDS > 0:
                keep_warm_task = asyncio.create_task(
                    _keep_warm(
                        CONTEXT.CONFIG.BGE_KEEPWARM_SECONDS, CONTEXT.CONFIG.BGE_M3_MAX_LENGTH
                    )
                )
                logger.info(f"Keep-warm every {CONTEXT.CONFIG.BGE_KEEPWARM_SECONDS}s enabled")

            # 6. Service is ready — log a structured boot summary and yield to FastAPI.
            # resolved_device is set by load(); it reflects the actual device in use.
            # BGE_FP16 from config is the *requested* value; bge_models.use_fp16 is the
            # *gated* value (forced false on CPU even if BGE_FP16=true was set).
            resolved_device = CONTEXT.bge_models.resolved_device or "unknown"
            gated_fp16 = CONTEXT.bge_models.use_fp16
            logger.info(
                f"\nBGE Server ready\n"
                f"  embed   : {CONTEXT.CONFIG.BGE_M3_MODEL}\n"
                f"  rerank  : {CONTEXT.CONFIG.BGE_RERANKER_MODEL}\n"
                f"  policy  : {CONTEXT.CONFIG.BGE_DEVICE} -> device: {resolved_device}\n"
                f"  fp16    : requested={CONTEXT.CONFIG.BGE_FP16}, active={gated_fp16}\n"
                f"  max_len : {CONTEXT.CONFIG.BGE_M3_MAX_LENGTH}\n"
                f"  batching: max_batch={CONTEXT.CONFIG.BGE_MAX_BATCH_SIZE}, "
                f"wait_ms={CONTEXT.CONFIG.BGE_MAX_WAIT_MS}, "
                f"queue={CONTEXT.CONFIG.BGE_MAX_QUEUE_SIZE}"
            )
            yield

        finally:
            # Shutdown — guard with hasattr so partial startup is still cleaned up gracefully.
            # Order matters: stop the batching engine FIRST (drains in-flight futures, prevents
            # new model calls) THEN unload the models (releases GPU/CPU memory). Reversing this
            # order would let scatter operations call into an unloaded model.
            logger.info(f"Shutting down BGE Server...")
            # Stop the keep-warm task before the engine/models so no touch races the unload.
            if keep_warm_task is not None:
                keep_warm_task.cancel()
                try:
                    await keep_warm_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            if hasattr(CONTEXT, "batching_engine"):
                await CONTEXT.batching_engine.stop()
            if hasattr(CONTEXT, "bge_models"):
                CONTEXT.bge_models.unload()

    return _lifespan
