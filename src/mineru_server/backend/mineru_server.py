# ====== Code Summary ======
# MineruServer: the MinerU2.5-Pro VLM parse micro-service as a model_server_core ModelServer. The core
# builds the app (lifespan with config validation + model service load/unload, gzip, typed error
# handler, GET /health); this subclass provides what is MinerU's own: the title, the model service
# (whose VLM loads LAZILY on the first /parse, so startup builds nothing), the POST /parse route, and
# the GPU gate that makes /health report UNHEALTHY on a host with no CUDA GPU.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from model_server_core import DeviceProbe, ModelServer, ModelService, NvidiaDriverDetector

# ====== Internal Project Imports ======
from config_loader import MineruServerConfig
from libs.mineru import MineruService, TorchCudaDetector

# ====== Local Project Imports ======
from .routers import ParseRoutes


class MineruServer(ModelServer[MineruServerConfig]):
    """
    The MinerU host: PDF in, reading-ordered per-page blocks (text / table HTML / formula LaTeX) out.

    Assembling it is cheap and torch-free: the heavy VLM is only built by the engine on the first
    /parse. The device is probed through the NVIDIA driver nodes first (so the common GPU case never
    imports torch), then through torch.

    Args:
        config (type[MineruServerConfig]): The injected configuration.
    """

    def __init__(self, config: type[MineruServerConfig]) -> None:
        super().__init__(
            config, device_probe=DeviceProbe([NvidiaDriverDetector(), TorchCudaDetector()])
        )
        self.service = MineruService(
            backend=config.MINERU_BACKEND,
            lang=config.MINERU_LANG,
            model_source=config.MINERU_MODEL_SOURCE,
            model_cache_home=config.MINERU_MODEL_CACHE_HOME,
            lock_wait_timeout_seconds=config.LOCK_WAIT_TIMEOUT_SECONDS,
        )

    # =======================
    #   Abstract contract
    # =======================
    @property
    def title(self) -> str:
        """Title of the FastAPI app."""
        return "MinerU2.5-Pro VLM parse service"

    def model_service(self) -> ModelService:
        """The parse service; always ready, since the VLM loads lazily on the first /parse."""
        return self.service

    def build_routes(self, app: FastAPI) -> None:
        """Register POST /parse at the root (no versioned prefix, like bge_server/paddle_server).

        Args:
            app (FastAPI): The application being assembled.
        """
        app.include_router(ParseRoutes(self.service, self.body_guard, self.input_validator).router)

    # =======================
    #   Hooks
    # =======================
    def health_blocker(self) -> str | None:
        """Report UNHEALTHY when the GPU is required and none is visible.

        MinerU2.5-Pro's VLM backend requires CUDA (it would fail at model load or run pathologically on
        CPU), so the container must never advertise a readiness it cannot honour.

        Returns:
            str | None: The reason, or None when a GPU is visible or `MINERU_REQUIRE_GPU` is off.
        """
        if self.config.MINERU_REQUIRE_GPU and not self.device_probe.cuda_available():
            return "No CUDA GPU visible; MinerU's VLM backend requires one."
        return None
