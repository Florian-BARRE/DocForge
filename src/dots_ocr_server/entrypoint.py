# ====== Code Summary ======
# Application entry point for the dots.ocr per-element layout VLM parse micro-service.
# This is the only file uvicorn targets: `uvicorn entrypoint:app` (run from /app/dots_ocr_server).
# Zero logic: the shared core's ServerEntrypoint applies the logging bootstrap and assembles the
# ASGI app of the DotsOcrServer built from the injected DotsOcrServerConfig. The dots.ocr model itself
# loads LAZILY on the first /parse request (see libs/dots_ocr/engine.py).

# ====== Third-Party Library Imports ======
from model_server_core import ServerEntrypoint

# ====== Internal Project Imports ======
from backend import DotsOcrServer
from config_loader import DotsOcrServerConfig

entrypoint = ServerEntrypoint(DotsOcrServer(DotsOcrServerConfig))
app = entrypoint.app

if __name__ == "__main__":
    entrypoint.run()
