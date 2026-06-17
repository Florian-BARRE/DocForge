---
paths:
  - "src/docforge/entrypoint.py"
  - "src/docforge/backend/**"
  - "src/docforge/backend/routers/**"
---

# FastAPI Project Rules

> These rules extend the general code rules and the Python rules. Apply all three together.

---

## Project Structure

```
project_root/
├── entrypoint.py              # App factory + CONTEXT bootstrap (served by uvicorn)
├── Dockerfile                 # See docker.md
│
├── config/                    # See python.md
│   ├── __init__.py
│   ├── runtime/
│   └── <yaml_group>/
│
├── libs/                      # Shared project libs (same as python.md)
│   └── <module>/              # e.g. libs/my_service/
│
├── backend/
│   ├── __init__.py            # Exposes create_app and CONTEXT
│   ├── app.py                 # FastAPI factory — assembles all routers
│   ├── context.py             # CONTEXT static class — typed service locator
│   ├── lifespan.py            # Bootstrap logic (startup/shutdown)
│   │
│   ├── routers/
│   │   ├── __init__.py        # Exposes all routers
│   │   └── <router_name>/
│   │       ├── __init__.py
│   │       ├── router.py      # Route definitions
│   │       ├── models.py      # Pydantic request/response models
│   │       └── helpers.py     # (optional) static helpers for this router
│   │
│   └── libs/                  # Backend-specific utilities (not shared with libs/)
│       └── utils/
│           └── error_handling.py
│
└── frontend/                  # Only if React is needed
    ├── vite.config.ts
    └── src/
```

Rules:
- `libs/` at the project root contains **shared domain modules** (services, clients, integrations) — same convention as python.md.
- `backend/libs/` contains **backend-specific utilities** (error handling, middleware helpers) that are not shared outside the backend package.
- `entrypoint.py` imports from both: `from libs.my_service import MyService` (shared) and internally the backend uses `from .libs.utils.error_handling import auto_handle_errors` (relative).

> **Note:** when combined with Docker, this entire tree lives inside `src/<app_name>/`.
> See docker.md for the full combined layout.

---

## `entrypoint.py` — Application Factory

This is the only file uvicorn targets (`uvicorn entrypoint:app`). Its sole responsibilities are:

1. Import `RUNTIME_CONFIG` **first** (registers `sys.path`).
2. Instantiate all high-level services and inject them into `CONTEXT`.
3. Call `create_app()` and assign the result to the module-level `app` variable.

```python
# ====== Code Summary ======
# Application entry point — wires services, injects CONTEXT, and creates the FastAPI app.

# ====== Standard Library Imports ======
from pathlib import Path

# ====== Third-Party Library Imports ======
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG          # MUST be first
from config import YAHOO_CONFIG, ALPHA_VANTAGE_CONFIG

from backend import CONTEXT, create_app
from libs.my_service import MyService


def _build_app() -> FastAPI:
    """
    Assemble and return a fully configured FastAPI application.

    Returns:
        FastAPI: The configured application instance.
    """
    # 1. Inject logger and config into CONTEXT
    CONTEXT.logger = loggerplusplus.bind(identifier="BACKEND")
    CONTEXT.RUNTIME_CONFIG = RUNTIME_CONFIG

    # 2. Instantiate and inject services
    CONTEXT.my_service = MyService(...)

    # 3. Create the FastAPI app
    fastapi_app = create_app(
        app_name=CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME,
        debug=CONTEXT.RUNTIME_CONFIG.FASTAPI_DEBUG_MODE,
    )

    # 4. Mount frontend static files (if applicable)
    fastapi_app.mount(
        "/",
        StaticFiles(directory=RUNTIME_CONFIG.PATH_ROOT_DIR_FRONTEND, html=True),
        name="static",
    )

    # 5. Add CORS middleware — origins read from RUNTIME_CONFIG
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=RUNTIME_CONFIG.CORS_ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return fastapi_app


app: FastAPI = _build_app()

__all__ = ["app"]
```

Rules:
- No business logic in `entrypoint.py` — only wiring and assembly.
- Every service the routes need must be available in `CONTEXT` before `create_app()` is called.
- The module-level `app` variable must always be named `app`.
- CORS origins are read from `RUNTIME_CONFIG.CORS_ALLOWED_ORIGINS` (a comma-separated env var cast to a list), never hardcoded.

---

## `context.py` — Typed Service Locator

`CONTEXT` is a static class with **type annotations only** — no values, no logic. It acts as a central registry for all shared services, configs, and runtime state.

```python
# ====== Code Summary ======
# Defines the shared application context (service locator) used across all routes and services.

# ====== Standard Library Imports ======
from typing import Any, Type

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerPlusPlus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from libs.my_service import MyService


class CONTEXT:
    """
    Shared application context — typed service locator.

    Type annotations only. All values are assigned at startup in entrypoint.py.
    Access via CONTEXT.attribute_name anywhere in the codebase.
    """

    # Logger
    logger: LoggerPlusPlus

    # Configuration
    RUNTIME_CONFIG: Type[RUNTIME_CONFIG]

    # Services
    my_service: MyService

    # Runtime state (populated during lifespan)
    active_tasks: dict[str, Any]
```

Rules:
- `CONTEXT` is never instantiated — all attributes are accessed as class-level attributes.
- Attributes are typed with their exact class, not `Any`, whenever possible.
- Runtime state (dicts, task registries) is initialized in `lifespan.py`, not here.
- Never import from `entrypoint.py` to avoid circular dependencies — `CONTEXT` is the bridge.

---

## `app.py` — FastAPI Factory

Assembles the `FastAPI` instance and registers all routers. No business logic here.

```python
# ====== Code Summary ======
# Creates the FastAPI application instance and registers all API routers.

# ====== Third-Party Library Imports ======
from fastapi import FastAPI

# ====== Local Project Imports ======
from .lifespan import lifespan
from .routers import health_router, sync_router, data_router
from .context import CONTEXT


def create_app(app_name: str, debug: bool) -> FastAPI:
    """
    Create and configure the FastAPI application instance.

    Args:
        app_name (str): Application title shown in OpenAPI docs.
        debug (bool): Enable debug mode.

    Returns:
        FastAPI: Configured application.
    """
    app = FastAPI(
        title=app_name,
        version="1.0.0",
        lifespan=lifespan(),
        debug=debug,
    )

    api_prefix = "/api/v1"
    app.include_router(router=health_router, prefix=api_prefix)
    app.include_router(router=sync_router, prefix=api_prefix)
    app.include_router(router=data_router, prefix=api_prefix)

    return app


__all__ = ["create_app"]
```

---

## `lifespan.py` — Bootstrap & Shutdown

The lifespan handles **everything that needs async initialization** and orderly shutdown. It is also the place where the full runtime configuration is printed to the logs.

Structure:
1. Print ASCII banner + app name.
2. Log all loaded configurations (runtime + YAML configs).
3. Initialize async services step by step, with numbered `log_step()` calls.
4. Yield control to FastAPI.
5. In `finally`: shut down all services in reverse order, using `hasattr` guards to handle partial startup failures.

```python
# ====== Code Summary ======
# Provides the FastAPI lifespan context manager for bootstrapping services and orderly shutdown.

# ====== Standard Library Imports ======
import asyncio
import unicodedata
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

# ====== Third-Party Library Imports ======
from pyfiglet import Figlet

# ====== Local Project Imports ======
from .context import CONTEXT

# Total number of startup steps — update this when adding/removing steps.
TOTAL_STEPS = 4


def lifespan() -> Any:
    """
    Return the FastAPI lifespan context manager factory.

    Returns:
        Any: Async context manager for FastAPI's lifespan parameter.
    """

    def log_step(step: int, message: str) -> None:
        """Log a numbered startup step."""
        CONTEXT.logger.info(f"\n[{step}/{TOTAL_STEPS}] {message}...")

    @asynccontextmanager
    async def _lifespan(app: Any) -> AsyncIterator[None]:
        _ = app
        try:
            # 1. Print startup banner
            banner = "\n" + Figlet(font="slant").renderText(
                "".join(
                    c for c in unicodedata.normalize("NFD", CONTEXT.RUNTIME_CONFIG.FASTAPI_APP_NAME)
                    if unicodedata.category(c) != "Mn"
                )
            )
            CONTEXT.logger.info(banner)

            # 2. Log runtime config
            log_step(1, "Runtime configuration")
            CONTEXT.logger.info(CONTEXT.RUNTIME_CONFIG)

            # 3. Log YAML configs (if any)
            log_step(2, "Application configuration")
            # CONTEXT.logger.info(YAHOO_CONFIG)

            # 4. Initialize services (one log_step per service)
            log_step(3, "Service initialization")
            await CONTEXT.my_service.start()

            # 5. Initialize runtime state dicts
            log_step(4, "Runtime state")
            CONTEXT.active_tasks = {}

            # 6. Yield — app is now running
            yield

        finally:
            # Shutdown in reverse order, guard each step with hasattr
            CONTEXT.logger.info(f"Shutting down...")

            if hasattr(CONTEXT, "my_service"):
                await CONTEXT.my_service.stop()

    return _lifespan
```

Rules:
- Always use `hasattr(CONTEXT, "attr")` guards in `finally` — a partial startup must still shut down cleanly.
- `TOTAL_STEPS` is a module-level constant — update it whenever you add or remove a startup step.
- Log all loaded configs right after the banner (runtime config, then YAML configs).
- Never raise from the `finally` block.

---

## Routers — Structure

Each router lives in its own sub-folder under `routers/`:

```
routers/
├── __init__.py             # Exposes all routers
└── health/
    ├── __init__.py
    ├── router.py           # Route definitions + @auto_handle_errors
    ├── models.py           # Pydantic request/response models for this router
    └── helpers.py          # (optional) static helper class
```

### `models.py`

Pydantic models for request bodies and responses. One file per router.

```python
from pydantic import BaseModel, Field


class MyResponse(BaseModel):
    """
    Response model for the /my-endpoint route.

    Attributes:
        id (str): Resource identifier.
        status (str): Current status.
    """
    id: str = Field(..., description="Resource identifier.")
    status: str = Field(..., description="Current status.")
```

### `router.py` — `@auto_handle_errors` on every endpoint

Every route **must** be decorated with `@auto_handle_errors`. The decorator must be placed **below** the `@router.get/post/...` decorator and **above** the function definition:

```python
# ====== Code Summary ======
# Route definitions for the health check endpoint.

# ====== Third-Party Library Imports ======
from fastapi import APIRouter

# ====== Internal Project Imports ======
from ...context import CONTEXT
from ...libs.utils.error_handling import auto_handle_errors
from .models import MyResponse

router = APIRouter()


@router.get("/ping", response_model=MyResponse)
@auto_handle_errors
async def ping() -> MyResponse:
    """
    Health check endpoint.

    Returns:
        MyResponse: Status response.
    """
    # 1. Return health status
    return MyResponse(id="health", status="ok")
```

Rules:
- `@router.get/post/...` is always the **outermost** decorator.
- `@auto_handle_errors` is always immediately above the function.
- Never catch generic exceptions in a route — let `@auto_handle_errors` handle them.
- Always declare a `response_model` on every route.

### `auto_handle_errors` — Error Decorator

This decorator must live in `backend/libs/utils/error_handling.py` and be reused across all routers. It handles both sync and async functions, catches all non-`HTTPException` errors, logs them with traceback, and returns an HTTP 500. **The traceback is only included in the response body when debug mode is active** — in production, only a generic error message is returned.

```python
# ====== Code Summary ======
# Provides the @auto_handle_errors decorator for automatic exception handling on all routes.

# ====== Standard Library Imports ======
import functools
import inspect
import traceback

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from ...context import CONTEXT


def _build_error_detail(func_name: str, exc: Exception, tb: str) -> dict:
    """
    Build the HTTP 500 response detail.

    In debug mode, includes the full traceback and function name.
    In production, returns only a generic error message.

    Args:
        func_name (str): Name of the failing function.
        exc (Exception): The caught exception.
        tb (str): Formatted traceback string.

    Returns:
        dict: Error detail dictionary.
    """
    if getattr(CONTEXT.RUNTIME_CONFIG, "FASTAPI_DEBUG_MODE", False):
        return {
            "error": str(exc),
            "traceback": tb,
            "function": func_name,
        }
    return {"error": "Internal server error."}


def auto_handle_errors(func):
    """
    Decorator to automatically handle unexpected exceptions for sync and async route functions.

    Logs the error with full traceback and raises an HTTPException (500).
    HTTPExceptions are always re-raised as-is.

    Args:
        func (Callable): The route function to wrap.

    Returns:
        Callable: Wrapped function with automatic error handling.
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail=_build_error_detail(func.__name__, exc, tb),
            )

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as exc:
            tb = traceback.format_exc()
            CONTEXT.logger.error(f"[{func.__name__}] {exc}\n{tb}")
            raise HTTPException(
                status_code=500,
                detail=_build_error_detail(func.__name__, exc, tb),
            )

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
```

---

## `routers/__init__.py`

Exposes all routers with clear section labels:

```python
# -------------------- Health --------------------- #
from .health.router import router as health_router

# -------------------- Data ----------------------- #
from .data.router import router as data_router

# ------------------- Public API ------------------ #
__all__ = [
    "health_router",
    "data_router",
]
```

---

## Frontend (React) — If Needed

If the project includes a React frontend, it lives in `/frontend` and is served as static files by FastAPI (see `entrypoint.py`).

Rules:
- Develop in an **object-oriented, component-based** style — one component per file.
- Create a **dedicated theme file** (`theme.js` or `theme.ts`) that centralizes all colors, font sizes, spacing, and design tokens. No hardcoded color values anywhere else in the codebase.
- Split components into small, single-responsibility files — no monolithic component files.
- Group by feature/domain, not by type (`components/health/HealthCard.tsx`, not `components/cards/HealthCard.tsx`).
- Use `vite` as the build tool (`vite.config.ts` at the frontend root).
- The built output (`dist/`) is what FastAPI mounts — always build before deploying.

---

## FastAPI-Specific RUNTIME_CONFIG Variables

Every FastAPI project must include these variables in `RUNTIME_CONFIG` (in addition to the mandatory `LOGGING_*` set from python.md):

```python
# ───── FastAPI ─────
FASTAPI_APP_NAME = env("FASTAPI_APP_NAME")
FASTAPI_DEBUG_MODE = env("FASTAPI_DEBUG_MODE", cast=bool)
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")  # Comma-separated string, split in entrypoint

# ───── Paths ─────
PATH_ROOT_DIR_FRONTEND = PATH_ROOT_DIR / "frontend" / "dist"
```

---

## General FastAPI Rules

- All services and shared state are accessed via `CONTEXT` — never import service instances directly in route files.
- Business logic belongs in `libs/` sub-modules, never in `router.py` files.
- `router.py` files contain only route definitions — they call services, format responses, and return models.
- Use Pydantic models for all request bodies and responses — never return raw dicts from routes.
- All routes must have a `response_model`.
- API prefix is always `/api/v1` — defined once in `app.py`, never repeated per router.
