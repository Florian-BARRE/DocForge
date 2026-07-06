# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built with src/docforge-rework/ as context (the worker needs shared/ + worker/):
#   docker build -f worker/Dockerfile -t docforge-rework-worker:latest .
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create the WORKER's dedicated virtual environment at /opt/venv
# - Install the locked base dependencies PLUS the heavy worker group
#   (docling, rapidocr-onnxruntime, pypdfium2, pillow) — the app image never carries them
# - Pre-download the tiktoken BPE cache so an offline/air-gapped worker never fetches at runtime
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

# Tell uv where to create the project environment (copied into the runtime stage).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata first to maximise Docker layer-cache reuse: dependency layers
# only rebuild when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./

# Install the locked dependencies for the WORKER image.
# --frozen: fail if the lock is out of sync; --no-dev: skip dev tooling;
# --group worker: the heavy model runtimes only this image needs.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group worker

# Pre-populate the tiktoken cache (the chunker's tokenizer): the first get_encoding()
# downloads BPE data over the network — baked here so runtime needs no egress.
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache
RUN /opt/venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

###############################################################################
# Stage 2: Runtime image (minimal Python runtime)
#
# Goal:
# - Contain only what the worker needs to run:
#     /opt/venv            -> the prebuilt environment (base + worker group)
#     /opt/tiktoken_cache  -> the pre-downloaded tokenizer data
#     /app/shared          -> the shared socle (pipelines, public_models, services)
#     /app/worker          -> the worker (entrypoint, config, backend)
# - Run the long-lived arq queue server as the container's process
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: no .pyc files written to disk
# - PYTHONUNBUFFERED: logs appear immediately in stdout/stderr
# - PATH: make the uv-built venv the active Python environment
# - TIKTOKEN_CACHE_DIR: point the tokenizer at the baked cache (no runtime download)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    TIKTOKEN_CACHE_DIR=/opt/tiktoken_cache

WORKDIR /app/worker

# Copy the prebuilt virtual environment and the baked tokenizer cache from the builder.
COPY --from=py-build /opt/venv /opt/venv
COPY --from=py-build /opt/tiktoken_cache /opt/tiktoken_cache

# Copy the shared socle then the worker itself (worker/config bootstraps the
# shared_libs alias from /app/shared/libs at startup).
COPY shared /app/shared
COPY worker /app/worker

# Start the queue server: arq loads WorkerSettings, connects Redis, runs startup
# (all store clients instantiated once), then polls the queue until SIGTERM.
CMD ["arq", "entrypoint.WorkerSettings"]
