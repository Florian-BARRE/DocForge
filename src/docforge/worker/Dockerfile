# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built with src/docforge/ as context (the worker needs shared/ + worker/):
#   docker build -f worker/Dockerfile -t docforge-worker:latest .
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

# Torch wheel variant: cpu (default, ~200 MB) or gpu (CUDA 12.4, multi-GiB).
# CPU keeps the image small enough for a CPU dev VM; docling runs fine on CPU torch.
#   GPU: docker build --build-arg TORCH_VARIANT=gpu ...  (+ NVIDIA Container Toolkit on the host)
ARG TORCH_VARIANT=cpu

# Install the locked dependencies for the WORKER image.
# --frozen: fail if the lock is out of sync; --no-dev: skip dev tooling;
# --group worker: the heavy model runtimes only this image needs;
# --extra ${TORCH_VARIANT}: steers torch to the cpu (or gpu) wheel index (see pyproject uv sources).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group worker --extra "${TORCH_VARIANT}"

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

# System shared libraries the model stack loads at runtime. docling's PDF/image path and the
# OpenCV pulled by rapidocr-onnxruntime link against X11/GL client libs even when run headless —
# without them the parse stage dies at import (e.g. "libxcb.so.1: cannot open shared object file").
# --no-install-recommends keeps the layer minimal; the apt lists are dropped to shrink the image.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libxcb1 \
        libxrender1 \
        libxext6 \
        libsm6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/worker

# Non-root runtime user with a real home directory: docling/rapidocr/huggingface_hub resolve
# their model cache from $HOME/.cache/huggingface (HF_HOME) by default, so unlike the app/mcp
# images this one needs a writable, addressable home — NOT nested under /app/worker or
# /app/shared, because docker-compose.dev.yml bind-mounts host source directly over both of
# those paths, which would shadow (and in prod, simply never seed) a cache dir placed inside
# them. --create-home materializes /home/appuser owned by the new user.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --create-home --home-dir /home/appuser \
        --shell /usr/sbin/nologin appuser

# Pin HOME explicitly (don't rely on nsswitch/passwd resolution) so huggingface_hub's default
# cache path ($HOME/.cache/huggingface) is deterministic regardless of how the container is run.
ENV HOME=/home/appuser

# WORKDIR above created /app/worker as root (it predates the COPYs below, so their --chown
# never touches it) — chown the directory itself too, or appuser can read everything inside it
# but can't create NEW entries (e.g. `logs/`) directly under it.
RUN chown appuser:appuser /app/worker

# Pre-create the exact cache directory Docker mounts the persistent volume onto (see
# docker-compose.yml's docforge_worker_hf_cache), owned by appuser. Docker seeds a freshly
# created named volume from whatever already exists (content + ownership) at its mount target
# in the image, so a fresh volume on a clean deploy comes up appuser-writable instead of
# root-owned (which would crash the first docling parse with a cache-write PermissionError).
RUN mkdir -p /home/appuser/.cache/huggingface && chown -R appuser:appuser /home/appuser

# Copy the prebuilt virtual environment and the baked tokenizer cache from the builder, owned by
# the runtime user (execute access to the venv, read access to the pre-populated tiktoken cache).
COPY --from=py-build --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=py-build --chown=appuser:appuser /opt/tiktoken_cache /opt/tiktoken_cache

# Copy the shared socle then the worker itself (worker/config bootstraps the
# shared_libs alias from /app/shared/libs at startup). --chown so appuser owns /app/worker and
# can create `logs/` under it at runtime if LOGGING_ENABLE_FILE is turned on.
COPY --chown=appuser:appuser shared /app/shared
COPY --chown=appuser:appuser worker /app/worker

# Drop root for the actual process — the apt install and chown steps above still ran as root,
# which is fine since only the final runtime layer's process user matters.
USER appuser

# Start the queue server: arq loads WorkerSettings, connects Redis, runs startup
# (all store clients instantiated once), then polls the queue until SIGTERM.
CMD ["arq", "entrypoint.WorkerSettings"]
