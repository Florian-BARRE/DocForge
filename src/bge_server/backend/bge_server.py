# ====== Code Summary ======
# BgeServer: the BGE model-suite micro-service as a model_server_core ModelServer. The core builds the
# app (lifespan with config validation + model load, typed error handler, GET /health); this subclass
# provides what is BGE's own: the title, the model service, the TEI-style inference routes, the
# gzip level knob, the health body with the model ids, and the async runtime (batching engine,
# warmup, keep-warm) wrapped around the core lifespan.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from model_server_core import (
    DeviceProbe,
    HealthResponse,
    HealthStatus,
    ModelServer,
    ModelService,
)

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig
from libs.bge_models import BgeModelsService, TorchCudaDetector

# ====== Local Project Imports ======
from .bge_health_response import BgeHealthResponse
from .routers import InferenceRoutes
from .runtime import BgeRuntime


class BgeServer(ModelServer[BgeServerConfig]):
    """
    The BGE host: dense + sparse + colbert embedding (BGE-M3) and rerank (BGE-reranker-v2-m3).

    Assembling it is cheap and torch-free: the models are only built by the core lifespan, on
    startup. The device is probed through torch (the library the models load through).

    Args:
        config (type[BgeServerConfig]): The injected configuration.
    """

    health_response_model = BgeHealthResponse

    def __init__(self, config: type[BgeServerConfig]) -> None:
        super().__init__(config, device_probe=DeviceProbe([TorchCudaDetector()]))
        # Device resolution (torch.cuda.is_available) is deferred to load(), inside the lifespan,
        # so this wiring step is cheap and has no ML-stack dependencies. max_concurrent is
        # forwarded so load() can auto-derive the torch thread budget.
        self.models = BgeModelsService(
            embed_model_id=config.BGE_M3_MODEL,
            rerank_model_id=config.BGE_RERANKER_MODEL,
            device_policy=config.DEVICE,
            fp16_requested=config.BGE_FP16,
            torch_num_threads=config.NUM_THREADS,
            embed_revision=config.BGE_M3_REVISION,
            rerank_revision=config.BGE_RERANKER_REVISION,
            load_reranker=config.BGE_LOAD_RERANKER,
            max_concurrent=config.BGE_MAX_CONCURRENT,
        )
        self.runtime = BgeRuntime(config, self.models)

    # =======================
    #   Abstract contract
    # =======================
    @property
    def title(self) -> str:
        """Title of the FastAPI app."""
        return "BGE model-suite (embed dense+sparse + rerank)"

    @property
    def version(self) -> str:
        """Version advertised in the OpenAPI document."""
        return "2.0.0"

    def model_service(self) -> ModelService:
        """The BGE models; their readiness drives GET /health."""
        return self.models

    def build_routes(self, app: FastAPI) -> None:
        """Register the TEI-contract inference routes at the root (no versioned prefix).

        The DocForge `tei` embed provider and `bge_reranker` rerank provider call
        /embed, /embed_sparse, /rerank (and /health) directly.

        Args:
            app (FastAPI): The application being assembled.
        """
        app.include_router(InferenceRoutes(self.config, self.runtime).router)

    # =======================
    #   Hooks
    # =======================
    def build_health(self, status: HealthStatus, ready: bool, detail: str | None) -> HealthResponse:
        """GET /health body: the core fields plus the two model identities."""
        return BgeHealthResponse(
            status=status.value,
            ready=ready,
            detail=detail,
            device=self.current_device(),
            embed_model=self.config.BGE_M3_MODEL,
            rerank_model=self.config.BGE_RERANKER_MODEL,
        )

    def configure_middlewares(self, app: FastAPI) -> None:
        """Compress large responses (dense/sparse embed batches) transparently.

        Callers must send `Accept-Encoding: gzip` (httpx/requests do this by default) to receive
        compressed bodies. The level is a config knob (BGE_GZIP_LEVEL): the default is cheap (1),
        not zlib's max (9), because this is an internal docker-bridge hop where CPU on the shared
        event loop is the bottleneck, not bandwidth.
        """
        if self.config.BGE_GZIP_ENABLED:
            app.add_middleware(
                GZipMiddleware,
                minimum_size=self.config.GZIP_MINIMUM_SIZE,
                compresslevel=self.config.BGE_GZIP_LEVEL,
            )

    # =======================
    #   Private Methods
    # =======================
    def _around_core_lifespan(
        self, core_lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]]
    ) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
        """Wrap the core lifespan so the async runtime lives inside it.

        The core hooks are sync, but the engine and keep-warm task must be stopped with `await`.
        Nesting keeps the required order: models loaded by the core, THEN the runtime starts; on
        exit the runtime stops FIRST, then the core unloads the models.
        """

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            async with core_lifespan(app):
                try:
                    await self.runtime.start()
                    yield
                finally:
                    await self.runtime.stop()

        return lifespan

    # =======================
    #   Public Methods
    # =======================
    def create_app(self) -> FastAPI:
        """Assemble the app with the runtime wrapped around the core lifespan."""
        app = super().create_app()
        core_lifespan: Any = app.router.lifespan_context
        app.router.lifespan_context = self._around_core_lifespan(core_lifespan)
        return app
