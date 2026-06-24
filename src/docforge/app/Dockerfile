# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Backend (FastAPI) image. Built from the repository root with src/ as context.
# Example:
#   docker build -f src/backend/Dockerfile -t docforge:latest src
#
# Multi-root layout: shared code lives in src/common/ (importable as `config` and
# `common_libs.*`), backend-dedicated code in src/backend/ (`backend`, `entrypoint`,
# `libs.*`). Both are copied into the image; entrypoint.py's path bootstrap registers
# /app/common and /app/backend on sys.path at startup.
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create a virtual environment at /opt/venv with the BASE production dependencies only.
# - The optional `worker` group (docling + torch/opencv) is deliberately NOT installed:
#   the backend never runs DoclingBackend.parse(), so it ships ~2-3 GB lighter. Only the
#   worker image (src/worker/Dockerfile) adds `--extra worker`.
# - The dependency contract (pyproject.toml/uv.lock) lives in src/common/ and is shared
#   by both images; copying it first isolates the dependency layer for cache efficiency.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

# Fixed venv path (/opt/venv) makes it trivial to copy into the runtime stage.
# UV_HTTP_TIMEOUT: raise the per-request timeout from 30s to 5 min for large wheels.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=300

# Copy only the shared dependency metadata first (cache layer independent of app code).
COPY docforge/common/pyproject.toml docforge/common/uv.lock /workspace/common/

# Install locked base dependencies (no worker extra, no dev tools).
# --frozen: fail if uv.lock is out of sync with pyproject.toml.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project /workspace/common

###############################################################################
# Stage 2: Frontend builder (Node 22 + Vite)
#
# Goal:
# - Install Node deps reproducibly with npm ci, compile the React bundle to dist/.
# - Only dist/ is carried into the runtime stage — no Node in production.
###############################################################################
FROM node:22-bookworm-slim AS ui-build

# CWD = frontend package root so npm ci / vite build resolve paths from package.json.
WORKDIR /workspace/frontend

# Copy package descriptors first to enable npm dependency-layer caching.
COPY docforge/app/frontend/package.json docforge/app/frontend/package-lock.json ./

RUN npm ci

# Copy the full frontend source and compile the production bundle.
COPY docforge/app/frontend/ ./
RUN npm run build

###############################################################################
# Stage 3: Runtime image (minimal Python 3.12 slim)
#
# Goal — a clean, minimal filesystem:
#     /app/common/                  → shared code (config, common_libs)
#     /app/backend/                 → backend code (entrypoint, backend pkg, libs)
#     /app/backend/frontend/dist    → compiled React bundle (served as static files)
#     /opt/venv/                    → prebuilt virtual environment (base deps only)
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# PYTHONDONTWRITEBYTECODE: no .pyc on disk. PYTHONUNBUFFERED: real-time logs.
# PATH: prepend the uv-built venv. (No QT_QPA_PLATFORM: the backend image has no OpenCV.)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# WORKDIR is the backend app root so `uvicorn entrypoint:app` finds entrypoint.py. The
# bootstrap at the top of entrypoint.py adds /app/common and /app/backend to sys.path.
WORKDIR /app/backend

# Prebuilt virtual environment (no uv, no build tools, no sources).
COPY --from=py-build /opt/venv /opt/venv

# Shared code + backend (app) code (rebuilt only when application code changes).
COPY docforge/common /app/common
COPY docforge/app /app/backend

# Compiled React bundle — FastAPI mounts /app/backend/frontend/dist at "/" (see entrypoint.py).
COPY --from=ui-build /workspace/frontend/dist /app/backend/frontend/dist

EXPOSE 8000

# entrypoint:app → the `app` variable in /app/backend/entrypoint.py.
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "8000"]
