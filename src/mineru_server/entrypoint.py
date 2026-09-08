# ====== Code Summary ======
# Application entry point for the MinerU2.5-Pro VLM parse micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/mineru_server).
# Responsibilities (in strict order):
#   1. Import MineruServerConfig FIRST — registers sys.path and configures logging sinks.
#   2. Inject config into CONTEXT.
#   3. Instantiate MineruService and inject into CONTEXT (the MinerU model itself loads LAZILY on the
#      first /parse request — see libs/mineru/engine.py).
#   4. Call create_app() and assign the result to the module-level `app` variable.
# No business logic here — only wiring and assembly.

# ====== Internal Project Imports ======
# MineruServerConfig MUST be the very first internal import: its class body calls sys.path.append()
# so that `from backend.*` and `from libs.*` can be resolved.
from config_loader import MineruServerConfig  # noqa: E402

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from backend import CONTEXT, create_app
from libs.mineru import MineruService

_logger = loggerplusplus.bind(identifier="MineruEntrypoint")


def _build_app() -> FastAPI:
    """
    Wire the service into CONTEXT and create the FastAPI application.

    Returns:
        FastAPI: The fully configured application instance.
    """
    # 1. Inject config into CONTEXT so lifespan and routes can read it.
    CONTEXT.CONFIG = MineruServerConfig

    # 2. Instantiate the parse service (the heavy MinerU model loads LAZILY inside the engine on the
    #    first /parse request, so this wiring step is cheap and never touches CUDA).
    CONTEXT.mineru = MineruService(
        backend=MineruServerConfig.MINERU_BACKEND,
        lang=MineruServerConfig.MINERU_LANG,
        model_source=MineruServerConfig.MINERU_MODEL_SOURCE,
        model_cache_home=MineruServerConfig.MINERU_MODEL_CACHE_HOME,
        lock_wait_timeout_seconds=MineruServerConfig.MINERU_LOCK_WAIT_TIMEOUT_SECONDS,
    )

    # 3. Create the FastAPI app (lifespan registered inside create_app).
    fastapi_app = create_app()
    _logger.debug(
        f"MinerU server wired: backend={MineruServerConfig.MINERU_BACKEND}, "
        f"require_gpu={MineruServerConfig.MINERU_REQUIRE_GPU}"
    )
    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
