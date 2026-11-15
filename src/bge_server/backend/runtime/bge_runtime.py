# ====== Code Summary ======
# BgeRuntime: the async half of the BGE service lifecycle. The core ModelServer lifespan validates the
# config and loads the models (sync hooks); BgeRuntime then builds and starts the dynamic-batching
# engine, runs the best-effort warmup and starts the keep-warm task, and on shutdown stops them in
# the order that keeps the models safe: keep-warm task first, then the engine (drains pending
# futures), and only afterwards (back in the core lifespan) the model unload. The routes read the
# engine and the model service from here; nothing is a global.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig
from libs.batching import BatchingEngine
from libs.bge_models import BgeModelsService

# ====== Local Project Imports ======
from .keep_warm import KeepWarm
from .model_warmup import ModelWarmup
from .ready_summary import ReadySummary

# Texts per model call on CPU when BGE_SUB_BATCH_SIZE=0 (auto) -- the cancellation granularity.
CPU_AUTO_SUB_BATCH_SIZE = 8


class BgeRuntime(LoggerClass):
    """
    Owns the batching engine and the keep-warm task on top of the (separately loaded) models.

    Args:
        config (type[BgeServerConfig]): The injected configuration.
        models (BgeModelsService): The model service; loaded by the core lifespan BEFORE `start`.
    """

    # Public attributes
    config: type[BgeServerConfig]
    models: BgeModelsService

    # Private attributes
    _engine: BatchingEngine | None
    _keep_warm: KeepWarm | None

    def __init__(self, config: type[BgeServerConfig], models: BgeModelsService) -> None:
        LoggerClass.__init__(self)
        self.config = config
        self.models = models
        self._engine = None
        self._keep_warm = None

    # =======================
    #   Properties
    # =======================
    @property
    def engine(self) -> BatchingEngine:
        """The batching engine the routes submit to.

        Raises:
            RuntimeError: Before `start()` has built it (a request outran the startup).
        """
        if self._engine is None:
            raise RuntimeError("The batching engine is not started yet.")
        return self._engine

    @engine.setter
    def engine(self, engine: BatchingEngine) -> None:
        """Inject an engine (the tests' seam; `start()` uses it for the real one)."""
        self._engine = engine

    # =======================
    #   Private Methods
    # =======================
    def _resolve_sub_batch_size(self) -> int:
        """Auto (0) sub-batch size: 8 on CPU so an abandoned batch stops within seconds; no
        splitting elsewhere (GPU passes are fast, and one big pass is more efficient)."""
        sub_batch = self.config.BGE_SUB_BATCH_SIZE
        if sub_batch == 0 and self.models.resolved_device == "cpu":
            return CPU_AUTO_SUB_BATCH_SIZE
        return sub_batch

    def _build_engine(self, sub_batch: int) -> BatchingEngine:
        """Build the engine from the config and the loaded models.

        The engine owns five per-op workers (dense / sparse / colbert / embed_all / rerank) plus
        TWO locks: embed_lock and rerank_lock (see BatchingEngine's class docstring).
        """
        return BatchingEngine(
            models=self.models,
            max_length=self.config.BGE_M3_MAX_LENGTH,
            max_batch_size=self.config.BGE_MAX_BATCH_SIZE,
            max_wait_ms=self.config.BGE_MAX_WAIT_MS,
            max_queue_size=self.config.BGE_MAX_QUEUE_SIZE,
            max_concurrent=self.models.max_concurrency,
            sub_batch_size=sub_batch,
            small_max_items=self.config.BGE_SMALL_REQUEST_MAX_ITEMS,
        )

    # =======================
    #   Public Methods
    # =======================
    async def start(self) -> None:
        """Start the engine, warm the models up and start the keep-warm task.

        Must run inside the lifespan, on the serving event loop: the workers are asyncio tasks that
        have to bind to the right loop (hot-reload safety).
        """
        # 1. Build and start the dynamic-batching engine (the models are already loaded).
        self.logger.info(f"START batching engine")
        sub_batch = self._resolve_sub_batch_size()
        self._engine = self._build_engine(sub_batch)
        self._engine.start()
        self.logger.info(f"END batching engine (sub_batch={sub_batch})")

        # 2. Warmup: one tiny dummy forward pass per inference path.
        ModelWarmup(self.models, self.config.BGE_M3_MAX_LENGTH).run()

        # 3. Keep-warm: periodic touch so an idle process's weights are never paged out.
        if self.config.BGE_KEEPWARM_SECONDS > 0:
            self._keep_warm = KeepWarm(
                self._engine,
                self.models.reranker_loaded,
                self.config.BGE_KEEPWARM_SECONDS,
                self.config.BGE_M3_MAX_LENGTH,
            )
            self._keep_warm.start()

        # 4. Ready: structured boot summary.
        ReadySummary(self.config, self.models).log(sub_batch)

    async def stop(self) -> None:
        """Stop the keep-warm task, then the engine; safe after a partial startup.

        Order matters: the engine is stopped BEFORE the models are unloaded (by the core lifespan,
        afterwards), or a scatter could call into an unloaded model.
        """
        if self._keep_warm is not None:
            await self._keep_warm.stop()
        if self._engine is not None:
            await self._engine.stop()
