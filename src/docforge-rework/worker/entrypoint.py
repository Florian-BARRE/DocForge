# ====== Code Summary ======
# Worker entry point — the arq target: `arq entrypoint.WorkerSettings` starts the long-lived
# queue server (connects Redis, runs backend.lifespan.startup, then polls the queue forever,
# executing up to WORKER_CONCURRENCY tasks in parallel; SIGTERM → orderly shutdown).
# Mirror of the app's entrypoint: config first (sys.path bootstrap), then the factory.

# ====== Internal Project Imports ======
from backend import create_worker_settings
from config import RUNTIME_CONFIG  # MUST be first — registers backend/libs + shared_libs

_ = RUNTIME_CONFIG  # imported for its bootstrap side effects (paths, logging sinks)

WorkerSettings = create_worker_settings()

__all__ = ["WorkerSettings"]
