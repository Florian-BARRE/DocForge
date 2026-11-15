# ====== Code Summary ======
# ModelServer: the abstract facade every DocForge model-host micro-service (bge, paddle, mineru,
# dots_ocr, and any future one) subclasses. It builds the FastAPI app and wires what the four servers
# used to duplicate: the lifespan (config validation, then startup / shutdown hooks), GET /health, the
# typed error handler, gzip, and the request guards (body cap, input validator). A server provides only
# what is its own: its title, its model service, its routes, and optional hooks.

# ====== Standard Library Imports ======
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar, Generic, TypeVar

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from model_server_core.config import ServerConfig
from model_server_core.device import DeviceProbe
from model_server_core.errors import ServerErrorHandler
from model_server_core.guards import InputValidator, RequestBodyGuard
from model_server_core.health import HealthResponse, HealthRoute, HealthStatus
from model_server_core.service import ModelService

# ====== Type Hints ======
ConfigT = TypeVar("ConfigT", bound=ServerConfig)


class ModelServer(ABC, LoggerClass, Generic[ConfigT]):
    """Abstract model-host server: subclass it, provide the three abstract members, done.

    Adding a server = a `ServerConfig` subclass + a `ModelServer` subclass + its routes. The base
    wires the app in this order: lifespan, gzip, error handler, GET /health, then `build_routes`.

    Args:
        config (type[ConfigT]): The injected configuration (read once, never re-read here).
        device_probe (DeviceProbe | None): Device probe; the torch-free driver probe by default. A
            server that decides on torch/paddle injects a probe holding its own detector.
        error_handler (ServerErrorHandler | None): Exception-to-answer mapping; the default typed
            500 + correlation id handler by default.
        input_validator (InputValidator | None): Body decoders; image + PDF by default.

    Raises:
        ValueError: If `config.MAX_BODY_BYTES` is not positive.
    """

    # Public attributes
    config: type[ConfigT]
    device_probe: DeviceProbe
    error_handler: ServerErrorHandler
    body_guard: RequestBodyGuard
    input_validator: InputValidator
    health_response_model: ClassVar[type[HealthResponse]] = HealthResponse

    def __init__(
        self,
        config: type[ConfigT],
        *,
        device_probe: DeviceProbe | None = None,
        error_handler: ServerErrorHandler | None = None,
        input_validator: InputValidator | None = None,
    ) -> None:
        LoggerClass.__init__(self)
        self.config = config
        self.device_probe = device_probe or DeviceProbe()
        self.error_handler = error_handler or ServerErrorHandler()
        self.body_guard = RequestBodyGuard(max_bytes=config.MAX_BODY_BYTES)
        self.input_validator = input_validator or InputValidator.from_config(config)

    # =======================
    #   Abstract contract
    # =======================
    @property
    @abstractmethod
    def title(self) -> str:
        """Title of the FastAPI app and name used in the startup / shutdown logs."""

    @abstractmethod
    def model_service(self) -> ModelService:
        """The hosted model (or an aggregate of pipelines); its readiness drives GET /health."""

    @abstractmethod
    def build_routes(self, app: FastAPI) -> None:
        """Register the server's own routers (`app.include_router(...)`) on `app`.

        Called after the shared wiring, so a route may use `self.body_guard`,
        `self.input_validator` and `self.model_service()`.

        Args:
            app (FastAPI): The application being assembled.
        """

    # =======================
    #   Hooks (optional)
    # =======================
    @property
    def version(self) -> str:
        """Version advertised in the OpenAPI document."""
        return "1.0.0"

    def startup(self) -> None:
        """Startup step run after config validation. Default: load the model service."""
        self.model_service().load()

    def shutdown(self) -> None:
        """Shutdown step, always run. Default: unload the model service (safe after a partial start)."""
        self.model_service().unload()

    def health_blocker(self) -> str | None:
        """A reason this host can NEVER serve (no GPU, missing CPU flag), or None. Default: none."""
        return None

    def build_health(self, status: HealthStatus, ready: bool, detail: str | None) -> HealthResponse:
        """Build the GET /health body; override (with `health_response_model`) to add fields.

        Args:
            status (HealthStatus): The computed status.
            ready (bool): Whether the host can serve.
            detail (str | None): Reason when not ready.

        Returns:
            HealthResponse: The body, with the probed device.
        """
        return HealthResponse(
            status=status.value, ready=ready, detail=detail, device=self.current_device()
        )

    def configure_middlewares(self, app: FastAPI) -> None:
        """Add the middlewares. Default: gzip above `config.GZIP_MINIMUM_SIZE`."""
        app.add_middleware(GZipMiddleware, minimum_size=self.config.GZIP_MINIMUM_SIZE)

    # =======================
    #   HealthSource port
    # =======================
    def is_ready(self) -> bool:
        """Whether the model service is ready (HealthSource port)."""
        return self.model_service().ready

    def current_device(self) -> str:
        """The probed device string, "cuda" or "cpu" (HealthSource port)."""
        return self.device_probe.device().value

    # =======================
    #   Private Methods
    # =======================
    @asynccontextmanager
    async def _lifespan(self, app: FastAPI) -> AsyncIterator[None]:
        """Startup and shutdown of the app, in narrated steps."""
        _ = app
        try:
            # 1. Log the configuration (secrets are masked by configplusplus), then validate it
            #    fail-fast BEFORE the slow model build: invalid config must abort startup at once.
            self.logger.info(f"START {self.title} (step 1/2: configuration)\n{self.config}")
            self.config.validate()

            # 2. Server-specific startup (default: build the model).
            self.logger.info(f"{self.title} (step 2/2: startup)")
            self.startup()
            self.logger.info(f"END startup of {self.title}: ready")
            yield
        finally:
            self.logger.info(f"Shutting down {self.title}...")
            self.shutdown()

    # =======================
    #   Public Methods
    # =======================
    def create_app(self) -> FastAPI:
        """Assemble the FastAPI application.

        Returns:
            FastAPI: The app, ready for uvicorn.
        """
        # 1. The app and its lifespan.
        app = FastAPI(title=self.title, version=self.version, lifespan=self._lifespan)

        # 2. Cross-cutting wiring: middlewares, then the exception handlers.
        self.configure_middlewares(app)
        self.error_handler.install(app)

        # 3. GET /health, then the server's own routes.
        app.include_router(HealthRoute(self, self.health_response_model).router)
        self.build_routes(app)
        return app
