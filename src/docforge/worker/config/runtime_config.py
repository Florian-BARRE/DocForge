# ====== Code Summary ======
# Worker (arq) runtime config — extends the shared BaseRuntimeConfig with worker-only
# settings the API never needs (arq concurrency/abort, metrics collection gate).
# Imported as `from config import RUNTIME_CONFIG` (resolves to this app's config tree).

# ====== Third-Party Library Imports ======
from configplusplus import env

# ====== Internal Project Imports ======
from base_config import BaseRuntimeConfig


class RUNTIME_CONFIG(BaseRuntimeConfig):
    """
    arq worker runtime configuration.

    Inherits every shared variable from BaseRuntimeConfig (logging, storage, providers…)
    and adds the settings used only by the ingestion worker process.
    """

    # ───── arq worker ─────
    # Max concurrent pipeline jobs per worker process (arq `max_jobs`).
    WORKER_MAX_JOBS: int = env("WORKER_MAX_JOBS", cast=int, default="10")
    # Enable arq job abort (required by POST /jobs/{id}/cancel). Read-only/safe.
    WORKER_ALLOW_ABORT: bool = env("WORKER_ALLOW_ABORT", cast=bool, default="true")

    # ───── Metrics collection (worker-only) ─────
    # Gate psutil/pynvml gauge sampling (the metrics collector is a worker-dedicated lib).
    OBS_METRICS_ENABLED: bool = env("OBS_METRICS_ENABLED", cast=bool, default="true")


__all__ = ["RUNTIME_CONFIG"]
