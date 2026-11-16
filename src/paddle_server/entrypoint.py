# ====== Code Summary ======
# Application entry point for the PaddleOCR micro-service (PP-StructureV3, OCR-only, PaddleOCR-VL).
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/paddle_server).
# Zero logic: the shared core's ServerEntrypoint applies the logging bootstrap and assembles the
# ASGI app of the PaddleServer built from the injected PaddleServerConfig. The pipelines are built by
# the core lifespan at startup (the VL one lazily, on its first request).

# ====== Third-Party Library Imports ======
from model_server_core import ServerEntrypoint

# ====== Internal Project Imports ======
from backend import PaddleServer
from config_loader import PaddleServerConfig

entrypoint = ServerEntrypoint(PaddleServer(PaddleServerConfig))
app = entrypoint.app

if __name__ == "__main__":
    entrypoint.run()
