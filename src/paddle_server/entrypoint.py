# ====== Code Summary ======
# Application entry point for the PP-StructureV3 layout-parsing micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/paddle_server).
# Responsibilities (in strict order):
#   1. Import PaddleServerConfig FIRST — registers sys.path and configures logging sinks.
#   2. Inject config into CONTEXT.
#   3. Instantiate PpStructureService and inject into CONTEXT (unbuilt — lifespan builds it).
#   4. Call create_app() and assign the result to the module-level `app` variable.
# No business logic here — only wiring and assembly.

# ====== Internal Project Imports ======
# PaddleServerConfig MUST be the very first internal import: its class body calls
# sys.path.append() so that `from backend.*` and `from libs.*` can be resolved.
from config_loader import PaddleServerConfig  # noqa: E402

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend import CONTEXT, create_app
from libs.ppstructure import PpStructureService

_logger = loggerplusplus.bind(identifier="PaddleEntrypoint")


def _build_app() -> FastAPI:
    """
    Wire all services into CONTEXT and create the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.
    """
    # 1. Inject config into CONTEXT so lifespan and routes can read it
    CONTEXT.CONFIG = PaddleServerConfig

    # 2. Instantiate the pipeline service (NOT built yet — lifespan calls .build()).
    # The heavy paddleocr/paddlex import is deferred to build(), so this wiring step is cheap.
    CONTEXT.ppstructure = PpStructureService(
        use_table_recognition=PaddleServerConfig.PADDLE_USE_TABLE_RECOGNITION,
        use_formula_recognition=PaddleServerConfig.PADDLE_USE_FORMULA_RECOGNITION,
        use_seal_recognition=PaddleServerConfig.PADDLE_USE_SEAL_RECOGNITION,
        use_doc_orientation_classify=PaddleServerConfig.PADDLE_USE_DOC_ORIENTATION_CLASSIFY,
        model_cache_home=PaddleServerConfig.PADDLE_PDX_CACHE_HOME,
        model_source=PaddleServerConfig.PADDLE_PDX_MODEL_SOURCE,
        lock_wait_timeout_seconds=PaddleServerConfig.PADDLE_LOCK_WAIT_TIMEOUT_SECONDS,
    )

    # 3. Create the FastAPI app (lifespan registered inside create_app)
    fastapi_app = create_app()
    _logger.debug(
        f"Paddle server wired: table={PaddleServerConfig.PADDLE_USE_TABLE_RECOGNITION}, "
        f"formula={PaddleServerConfig.PADDLE_USE_FORMULA_RECOGNITION}"
    )
    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
