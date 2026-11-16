# ====== Code Summary ======
# PaddleServer: the PaddleOCR micro-service (PP-StructureV3 layout parsing, OCR-only, PaddleOCR-VL) as
# a model_server_core ModelServer. The core builds the app (lifespan with config validation + model
# service load/unload, gzip, typed error handler, GET /health); this subclass provides what is
# Paddle's own: the title, the three pipeline services behind one model service, the three POST routes,
# and the AVX gate that makes /health report UNHEALTHY on a CPU PaddlePaddle would SIGILL on.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from model_server_core import CpuFeatureProbe, DeviceProbe, ModelServer, ModelService

# ====== Internal Project Imports ======
from config_loader import PaddleServerConfig
from libs.paddle_models import PaddleCudaDetector, PaddleModelsService
from libs.paddleocr import PaddleOcrService
from libs.paddleocr_vl import PaddleOcrVlService
from libs.ppstructure import PpStructureService

# ====== Local Project Imports ======
from .routers import LayoutParsingRoutes, OcrRoutes, VlParsingRoutes


class PaddleServer(ModelServer[PaddleServerConfig]):
    """
    The Paddle host: PDF in, reading-ordered per-page blocks out (PP-StructureV3 and PaddleOCR-VL), and
    image in, a single reading out (PaddleOCR).

    Assembling it is cheap and paddle-free: the heavy paddleocr/paddlex import is deferred to the
    pipelines' `load()`, run by the core lifespan on startup. The device is probed through
    PaddlePaddle's own runtime check only (the library the pipelines run on, not torch): the -cpu image
    on a host that exposes the NVIDIA driver still reports "cpu", as the inference runs on the CPU wheel.

    Args:
        config (type[PaddleServerConfig]): The injected configuration.
    """

    def __init__(self, config: type[PaddleServerConfig]) -> None:
        super().__init__(config, device_probe=DeviceProbe([PaddleCudaDetector()]))
        self.cpu_features = CpuFeatureProbe()
        # The three pipelines are NOT built here: the core lifespan loads them (PP-StructureV3 and
        # PaddleOCR at startup, PaddleOCR-VL lazily on its first request). The model cache and source
        # are only logged by the services (paddlex reads them from the environment itself).
        self.ppstructure = PpStructureService(
            use_table_recognition=config.PADDLE_USE_TABLE_RECOGNITION,
            use_formula_recognition=config.PADDLE_USE_FORMULA_RECOGNITION,
            use_seal_recognition=config.PADDLE_USE_SEAL_RECOGNITION,
            use_doc_orientation_classify=config.PADDLE_USE_DOC_ORIENTATION_CLASSIFY,
            model_cache_home=config.PADDLE_PDX_CACHE_HOME,
            model_source=config.PADDLE_PDX_MODEL_SOURCE,
            lock_wait_timeout_seconds=config.LOCK_WAIT_TIMEOUT_SECONDS,
        )
        # A SEPARATE PaddleOCR instance from ppstructure: pure text det+rec, no layout.
        self.paddleocr = PaddleOcrService(
            lang=config.PADDLE_OCR_LANG,
            use_textline_orientation=config.PADDLE_OCR_USE_TEXTLINE_ORIENTATION,
            model_cache_home=config.PADDLE_PDX_CACHE_HOME,
            model_source=config.PADDLE_PDX_MODEL_SOURCE,
            lock_wait_timeout_seconds=config.LOCK_WAIT_TIMEOUT_SECONDS,
        )
        # Heavy sub-pipelines default OFF (overridable per request); reuses the shared model cache and
        # lock-wait timeout (no new env var).
        self.paddleocr_vl = PaddleOcrVlService(
            use_chart_recognition=False,
            use_seal_recognition=False,
            use_ocr_for_image_block=False,
            model_cache_home=config.PADDLE_PDX_CACHE_HOME,
            model_source=config.PADDLE_PDX_MODEL_SOURCE,
            lock_wait_timeout_seconds=config.LOCK_WAIT_TIMEOUT_SECONDS,
        )
        self.models = PaddleModelsService(self.ppstructure, self.paddleocr, self.paddleocr_vl)

    # =======================
    #   Abstract contract
    # =======================
    @property
    def title(self) -> str:
        """Title of the FastAPI app."""
        return "PaddleOCR PP-StructureV3 layout-parsing service"

    def model_service(self) -> ModelService:
        """The three pipelines; the two eager ones drive GET /health readiness."""
        return self.models

    def build_routes(self, app: FastAPI) -> None:
        """Register the layout-parsing, VL-parsing and OCR routes at the root (no versioned prefix).

        Args:
            app (FastAPI): The application being assembled.
        """
        guards = (self.body_guard, self.input_validator)
        app.include_router(LayoutParsingRoutes(self.ppstructure, *guards).router)
        app.include_router(VlParsingRoutes(self.paddleocr_vl, *guards).router)
        app.include_router(OcrRoutes(self.paddleocr, *guards).router)

    # =======================
    #   Hooks
    # =======================
    def health_blocker(self) -> str | None:
        """Report UNHEALTHY on a CPU without AVX.

        The PaddlePaddle 3.x wheels are compiled with AVX and SIGILL on the FIRST real inference on a
        CPU without it, while the pipeline build still succeeds, so this is the only thing that stops
        the container advertising a readiness it cannot honour.

        Returns:
            str | None: The reason, or None when AVX is present (or cannot be ruled out).
        """
        if not self.cpu_features.supports("avx"):
            return "CPU lacks AVX support required by PaddlePaddle; inference would crash."
        return None
