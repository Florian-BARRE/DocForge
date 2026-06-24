# ====== Code Summary ======
# Application entry point for the BGE model-suite micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/bge_server).
# Responsibilities (in strict order):
#   1. Import BgeServerConfig FIRST — registers sys.path and configures logging sinks.
#   2. Inject config into CONTEXT.
#   3. Instantiate BgeModelsService and inject into CONTEXT (unloaded — lifespan loads models).
#   4. Call create_app() and assign the result to the module-level `app` variable.
# No business logic here — only wiring and assembly.

# ====== Internal Project Imports ======
# BgeServerConfig MUST be the very first internal import: its class body calls
# sys.path.append() so that `from backend.*` and `from libs.*` can be resolved.
from config_loader import BgeServerConfig  # noqa: E402

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend import CONTEXT, create_app
from libs.bge_models import BgeModelsService

_logger = loggerplusplus.bind(identifier="BGEEntrypoint")


def _build_app() -> FastAPI:
    """
    Wire all services into CONTEXT and create the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.
    """
    # 1. Inject config into CONTEXT so lifespan and routes can read it
    CONTEXT.CONFIG = BgeServerConfig

    # 2. Instantiate the model service (models are NOT loaded yet — lifespan calls .load()).
    # Device resolution (torch.cuda.is_available) is deferred to load() inside the lifespan,
    # not done here, so this wiring step is cheap and has no ML-stack dependencies.
    CONTEXT.bge_models = BgeModelsService(
        embed_model_id=BgeServerConfig.BGE_M3_MODEL,
        rerank_model_id=BgeServerConfig.BGE_RERANKER_MODEL,
        device_policy=BgeServerConfig.BGE_DEVICE,
        fp16_requested=BgeServerConfig.BGE_FP16,
    )

    # 3. Create the FastAPI app (lifespan registered inside create_app)
    fastapi_app = create_app()
    _logger.debug(
        f"BGE service wired: embed={BgeServerConfig.BGE_M3_MODEL}, "
        f"rerank={BgeServerConfig.BGE_RERANKER_MODEL}, "
        f"device_policy={BgeServerConfig.BGE_DEVICE}"
    )
    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
