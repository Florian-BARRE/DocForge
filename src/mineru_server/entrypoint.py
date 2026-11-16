# ====== Code Summary ======
# Application entry point for the MinerU2.5-Pro VLM parse micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/mineru_server).
# Zero logic: the shared core's ServerEntrypoint applies the logging bootstrap and assembles the
# ASGI app of the MineruServer built from the injected MineruServerConfig. The MinerU model itself
# loads LAZILY on the first /parse request (see libs/mineru/engine.py).

# ====== Third-Party Library Imports ======
from model_server_core import ServerEntrypoint

# ====== Internal Project Imports ======
from backend import MineruServer
from config_loader import MineruServerConfig

entrypoint = ServerEntrypoint(MineruServer(MineruServerConfig))
app = entrypoint.app

if __name__ == "__main__":
    entrypoint.run()
