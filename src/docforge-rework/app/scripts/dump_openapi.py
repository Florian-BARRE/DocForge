# ====== Code Summary ======
# CI/dev helper — prints the backend's CURRENT OpenAPI schema to stdout, built the exact same way
# app/entrypoint.py does (config imported first to wire sys.path + register the shared_libs alias,
# then the real FastAPI app object via create_app). Nothing is contacted over the network: FastAPI's
# .openapi() only introspects routes/response models, and Database/QueueClient hold their connection
# settings LAZILY at construction (see entrypoint.py's _build_app) — so this runs fully serviceless,
# with no compose stack required. Any DSN/URL env var below can be a placeholder.
#
# Usage (from src/docforge-rework/, the uv project root):
#   uv run python app/scripts/dump_openapi.py > openapi.json
#
# Requires the same env vars as the app (see services/docforge-rework/.env.example). Set
# LOGGING_ENABLE_CONSOLE=false (and LOGGING_ENABLE_FILE=false) for this invocation — the console
# sink writes to this same stdout and would corrupt the JSON output otherwise.

# ====== Standard Library Imports ======
import json
import pathlib
import sys

# APP_DIR (src/docforge-rework/app) must be on sys.path BEFORE `entrypoint` is imported, so its own
# `from config import RUNTIME_CONFIG` / `from backend import ...` resolve — mirrors how
# tests/units/api/conftest.py boots the same app object for the unit suite.
APP_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from entrypoint import app  # noqa: E402 — import deferred until APP_DIR is on sys.path


def main() -> None:
    """Print the FastAPI app's current OpenAPI schema as compact JSON to stdout."""
    sys.stdout.write(json.dumps(app.openapi()))


if __name__ == "__main__":
    main()
