# ====== Code Summary ======
# Application entry point for the dots.ocr per-element layout VLM parse micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/dots_ocr_server).
# Responsibilities (in strict order):
#   1. Import DotsOcrServerConfig FIRST — registers sys.path and configures logging sinks.
#   2. Inject config into CONTEXT.
#   3. Instantiate DotsOcrService and inject into CONTEXT (the transformers model itself loads LAZILY on the
#      first /parse request — see libs/dots_ocr/engine.py).
#   4. Call create_app() and assign the result to the module-level `app` variable.
# No business logic here — only wiring and assembly.

# ====== Internal Project Imports ======
# DotsOcrServerConfig MUST be the very first internal import: its class body calls sys.path.append()
# so that `from backend.*` and `from libs.*` can be resolved.
from config_loader import DotsOcrServerConfig  # noqa: E402

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend import CONTEXT, create_app
from libs.dots_ocr import DotsOcrService

_logger = loggerplusplus.bind(identifier="DotsOcrEntrypoint")


def _build_app() -> FastAPI:
    """
    Wire the service into CONTEXT and create the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.
    """
    # 1. Inject config into CONTEXT so lifespan and routes can read it.
    CONTEXT.CONFIG = DotsOcrServerConfig

    # 2. Instantiate the parse service (the heavy transformers model loads LAZILY inside the engine on the
    #    first /parse request, so this wiring step is cheap and never touches CUDA).
    CONTEXT.dots_ocr = DotsOcrService(
        model_path=DotsOcrServerConfig.DOTS_OCR_MODEL_PATH,
        model_cache_home=DotsOcrServerConfig.DOTS_OCR_MODEL_CACHE_HOME,
        render_dpi=DotsOcrServerConfig.DOTS_OCR_RENDER_DPI,
        max_pages=DotsOcrServerConfig.DOTS_OCR_MAX_PAGES,
        max_tokens=DotsOcrServerConfig.DOTS_OCR_MAX_TOKENS,
        image_factor=DotsOcrServerConfig.DOTS_OCR_IMAGE_FACTOR,
        min_pixels=DotsOcrServerConfig.DOTS_OCR_MIN_PIXELS,
        max_pixels=DotsOcrServerConfig.DOTS_OCR_MAX_PIXELS,
        lock_wait_timeout_seconds=DotsOcrServerConfig.DOTS_OCR_LOCK_WAIT_TIMEOUT_SECONDS,
    )

    # 3. Create the FastAPI app (lifespan registered inside create_app).
    fastapi_app = create_app()
    _logger.debug(
        f"dots.ocr server wired: model={DotsOcrServerConfig.DOTS_OCR_MODEL_PATH}, "
        f"require_gpu={DotsOcrServerConfig.DOTS_OCR_REQUIRE_GPU}"
    )
    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
