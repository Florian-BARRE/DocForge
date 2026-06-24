# ====== Code Summary ======
# App (FastAPI) runtime config — extends the shared BaseRuntimeConfig with web-only
# settings the worker never needs (FastAPI, CORS, SSE fan-out, resource admission).
# Imported as `from config import RUNTIME_CONFIG` (resolves to this app's config tree).

# ====== Third-Party Library Imports ======
from configplusplus import env

# ====== Internal Project Imports ======
from base_config import BaseRuntimeConfig


class RUNTIME_CONFIG(BaseRuntimeConfig):
    """
    FastAPI app runtime configuration.

    Inherits every shared variable from BaseRuntimeConfig (logging, storage, providers…)
    and adds the web-facing settings used only by the API process.
    """

    # ───── FastAPI ─────
    FASTAPI_APP_NAME: str = env("FASTAPI_APP_NAME", default="DocForge")
    FASTAPI_DEBUG_MODE: bool = env("FASTAPI_DEBUG_MODE", cast=bool, default="false")
    CORS_ALLOWED_ORIGINS: str = env("CORS_ALLOWED_ORIGINS", default="http://localhost:5173")
    # Application version surfaced in OpenAPI docs and the /health/ping endpoint.
    APP_VERSION: str = env("APP_VERSION", default="0.1.0")

    # ───── Real-time streaming (brick C) ─────
    # SSE comment-ping cadence (s) — keeps proxies/LBs from killing idle streams.
    SSE_KEEPALIVE_SECONDS: int = env("SSE_KEEPALIVE_SECONDS", cast=int, default="15")
    # Per-client SSE fan-out queue size; on overflow the broadcaster drops the oldest
    # event so one slow browser cannot grow memory unboundedly (back-pressure).
    SSE_CLIENT_QUEUE_MAXSIZE: int = env("SSE_CLIENT_QUEUE_MAXSIZE", cast=int, default="100")

    # ───── Resource admission / back-pressure (brick D) ─────
    # The enqueue gate lives in the API process (backend/libs/admission), never the worker.
    ADMISSION_ENABLED: bool = env("ADMISSION_ENABLED", cast=bool, default="true")
    ADMISSION_MAX_QUEUE_DEPTH: int = env("ADMISSION_MAX_QUEUE_DEPTH", cast=int, default="0")
    ADMISSION_MAX_IN_FLIGHT_GLOBAL: int = env("ADMISSION_MAX_IN_FLIGHT_GLOBAL", cast=int, default="0")


__all__ = ["RUNTIME_CONFIG"]
