# ====== Code Summary ======
# Application entry point for the BGE model-suite micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/bge_server).
# Zero logic: the shared core's ServerEntrypoint applies the logging bootstrap and assembles the
# ASGI app of the BgeServer built from the injected BgeServerConfig.

# ====== Third-Party Library Imports ======
from model_server_core import ServerEntrypoint

# ====== Internal Project Imports ======
from backend import BgeServer
from config_loader import BgeServerConfig

entrypoint = ServerEntrypoint(BgeServer(BgeServerConfig))
app = entrypoint.app

if __name__ == "__main__":
    entrypoint.run()
