# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as context.
# Example:
#   docker build -f src/docforge/Dockerfile -t docforge:latest src
#
# WORKDIR is set to /app/docforge (not /app) so that Python's CWD is at the
# package root — this makes `from config import RUNTIME_CONFIG` resolve to
# /app/docforge/config/ without needing an explicit sys.path manipulation
# at the container level.
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create a virtual environment at /opt/venv with all production dependencies.
# - Separate dependency installation from application code for layer-cache efficiency:
#   pyproject.toml/uv.lock layer is only rebuilt when dependencies change.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# Neutral build workspace — all paths inside the stage use /workspace as their root.
WORKDIR /workspace

# Tell uv where to create the project virtual environment.
# Using a fixed path (/opt/venv) makes it easy to copy to the runtime stage.
# UV_HTTP_TIMEOUT: raise the per-request timeout from the 30s default to 5 minutes.
# Large CUDA/ML wheels (nvidia-curand, triton, scipy) exceed 30s on slow links.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=300

# Copy only the lock metadata first.
# Docker caches this layer independently of application code changes.
# Dependency install is re-triggered only when pyproject.toml or uv.lock changes.
COPY docforge/pyproject.toml docforge/uv.lock /workspace/docforge/

# Install production dependencies from the locked file.
# --frozen: fail if uv.lock is out of sync with pyproject.toml (safety check).
# --no-dev:  skip development-only packages (test, lint, type-checking tools).
# cache mount: avoids re-downloading packages on repeated local builds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project /workspace/docforge

###############################################################################
# Stage 2: Frontend builder (Node 22 + Vite)
#
# Goal:
# - Install Node dependencies reproducibly with npm ci.
# - Compile the React/Vite app into a static bundle (frontend/dist/).
# - Only this dist/ directory is carried into the runtime stage — no Node in prod.
###############################################################################
FROM node:22-bookworm-slim AS ui-build

# Set working directory to the frontend package root so npm ci and vite build
# resolve paths relative to package.json (Vite expects CWD = frontend root).
WORKDIR /workspace/docforge/frontend

# Copy package descriptors first to enable npm dependency-layer caching.
# npm ci is only re-run when package.json or package-lock.json changes.
COPY docforge/frontend/package.json docforge/frontend/package-lock.json ./

# Reproducible install strictly from package-lock.json.
RUN npm ci

# Copy the full frontend source and compile the production bundle.
COPY docforge/frontend/ ./
RUN npm run build

###############################################################################
# Stage 3: Runtime image (minimal Python 3.12 slim)
#
# Goal:
# - Contain only what is needed to run DocForge.
# - Expose a clean, minimal filesystem:
#     /app/docforge/              → application source code
#     /app/docforge/frontend/dist → compiled React bundle (served as static files)
#     /opt/venv/                  → prebuilt virtual environment
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# PYTHONDONTWRITEBYTECODE: prevents .pyc bytecode files from being written to disk.
#   Reduces container image bloat; Python will recompile from .py at startup (fast).
# PYTHONUNBUFFERED: forces stdout/stderr to flush immediately.
#   Ensures container logs are visible in real time via `docker logs`.
# PATH: prepend the uv-built venv so its Python + executables are used by default.
# QT_QPA_PLATFORM=offscreen: prevents OpenCV/Qt from trying to connect to X11 (libxcb.so.1).
#   Docling imports OpenCV which bundles Qt plugins; without a display, the xcb platform
#   plugin would fail at runtime. "offscreen" uses a framebuffer backend — no X11 needed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    QT_QPA_PLATFORM=offscreen

# Set working directory to /app/docforge (the docforge package root).
# uvicorn is started from this directory so `from config import RUNTIME_CONFIG`
# resolves to /app/docforge/config/ without extra PYTHONPATH configuration.
WORKDIR /app/docforge

# Copy the prebuilt virtual environment from the py-build stage.
# Only the compiled environment is transferred — no uv, no build tools, no sources.
COPY --from=py-build /opt/venv /opt/venv

# Copy the DocForge application source tree.
# This layer is rebuilt whenever application code changes (fast after dependency cache hit).
COPY docforge /app/docforge

# Copy the compiled React bundle from the ui-build stage.
# FastAPI mounts this directory as static files at "/" (see entrypoint.py).
COPY --from=ui-build /workspace/docforge/frontend/dist /app/docforge/frontend/dist

# Expose the port uvicorn listens on (matched by docker-compose.yml and CMD below).
EXPOSE 8000

# Start the FastAPI application.
# entrypoint:app refers to the `app` variable in /app/docforge/entrypoint.py.
# --host 0.0.0.0: listen on all interfaces (required inside a container).
# --port 8000: standard FastAPI port, published via compose.
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "8000"]
