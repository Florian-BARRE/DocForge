# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built with src/docforge-rework/ as context (the app needs shared/ + app/):
#   docker build -f app/Dockerfile -t docforge-rework-app:latest .
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create the APP's dedicated virtual environment at /opt/venv
# - Install ONLY the locked base dependencies — the heavy worker group (docling,
#   rapidocr, pypdfium2, pillow) never enters this image: the app describes and
#   validates pipelines, it never executes them (lazy imports make that safe)
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

# Tell uv where to create the project environment (copied into the runtime stage).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata first to maximise Docker layer-cache reuse: dependency layers
# only rebuild when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./

# Install the locked BASE dependencies only.
# --frozen: fail if the lock is out of sync; --no-dev: skip dev tooling;
# no --group worker: this is what keeps the app image light.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

###############################################################################
# Stage 2: Frontend builder (Node + Vite)
#
# Goal:
# - Build the production UI bundle IN the image, so a fresh `--build` never ships
#   a missing or stale dist/ (previously relied on a host-built dist/ being present
#   in the build context — silently absent/stale on a clean checkout or CI runner).
# - node:22-bookworm-slim matches the version used by the rework_frontend dev
#   service (docker-compose.rework.dev.yml) so dev/prod build with the same Node.
###############################################################################
FROM node:22-bookworm-slim AS ui-build

WORKDIR /workspace/frontend

# Copy package descriptors first so the npm layer only rebuilds when they change.
COPY app/frontend/package.json app/frontend/package-lock.json ./

# Reproducible install strictly from the lockfile (no lockfile drift, no network
# resolution surprises).
RUN npm ci

# Copy the frontend source and compile the production bundle into dist/.
COPY app/frontend/ ./
RUN npm run build

###############################################################################
# Stage 3: Runtime image (minimal Python runtime)
#
# Goal:
# - Contain only what the app needs to run:
#     /opt/venv               -> the prebuilt light environment
#     /app/shared             -> the shared socle (pipelines, public_models, services)
#     /app/app                -> the FastAPI app (entrypoint, config, backend)
#     /app/app/frontend/dist  -> the compiled UI bundle, built above (not host state)
# - Serve the API with uvicorn as the container's process
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: no .pyc files written to disk
# - PYTHONUNBUFFERED: logs appear immediately in stdout/stderr
# - PATH: make the uv-built venv the active Python environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app/app

# Copy the prebuilt virtual environment from the builder.
COPY --from=py-build /opt/venv /opt/venv

# Copy the shared socle then the app itself (app/config bootstraps the
# shared_libs alias from /app/shared/libs at startup).
COPY shared /app/shared
COPY app /app/app

# Overlay the compiled UI bundle from the ui-build stage, replacing whatever
# dist/ (if any) came along in the COPY above.
COPY --from=ui-build /workspace/frontend/dist /app/app/frontend/dist

# FastAPI port served by uvicorn below.
EXPOSE 8000

# Start the API: uvicorn loads entrypoint.py (config bootstrap + CONTEXT wiring).
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "8000"]
