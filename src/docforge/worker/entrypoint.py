# ====== Code Summary ======
# Worker entry point — the arq target: `arq entrypoint.WorkerSettings` starts the long-lived
# queue server (connects Redis, runs backend.lifespan.startup, then polls the queue forever,
# executing up to WORKER_CONCURRENCY tasks in parallel; SIGTERM → orderly shutdown).
# Mirror of the app's entrypoint: config first (sys.path bootstrap), then the factory.

# ====== Internal Project Imports ======
# RUNTIME_CONFIG MUST be imported and evaluated FIRST: its class body registers the ``shared_libs``
# alias and puts backend/libs on sys.path, which ``backend`` and everything it pulls in rely on. The
# ``_ = RUNTIME_CONFIG`` line below forces that evaluation AND splits the import block, so isort can
# never re-float ``backend`` above ``config`` (both are first-party, so a single sorted block would
# order them alphabetically — backend first — silently breaking the bootstrap contract).
from config import RUNTIME_CONFIG

_ = RUNTIME_CONFIG  # evaluate the bootstrap side effects (sys.path + shared_libs alias) before backend

from backend import create_worker_settings  # noqa: E402 — must import AFTER the bootstrap above

WorkerSettings = create_worker_settings()

__all__ = ["WorkerSettings"]
