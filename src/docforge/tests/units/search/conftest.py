# ====== Code Summary ======
# Puts the app root (app/) on sys.path for the search unit package so `from backend...` and
# `from config...` resolve, exactly like the api conftest's fastapi_app fixture does — but WITHOUT
# importing the app (no entrypoint boot, no FastAPI/DB construction): these are pure app-side search
# units (the emitter/probe/read-port), not HTTP tests. Adding only the PATH is safe: the worker ROOT
# is never added (root conftest adds only worker/backend/libs), so there is no top-level `backend`
# package collision between app and worker.

# ====== Standard Library Imports ======
import pathlib
import sys

APP_DIR = pathlib.Path(__file__).resolve().parents[3] / "app"

# Register the app root at collection time so top-level `backend.*` / `config` imports resolve.
_app_dir_str = str(APP_DIR)
if _app_dir_str not in sys.path:
    sys.path.insert(0, _app_dir_str)
