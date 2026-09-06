# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as build context.
# Example:
#   docker build -f src/paddle_server/Dockerfile -t docforge-paddle-server:latest src
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Sync the locked production dependencies from uv.lock into a virtual environment
#   at /opt/venv, selecting the correct paddlepaddle wheel variant via TORCH_VARIANT.
# - TORCH_VARIANT=cpu  (default) installs paddlepaddle 3.3.1 from plain PyPI (~100 MB CPU
#   wheel, no CUDA payload). Target runtime image size: ~1.2-1.5 GB.
# - TORCH_VARIANT=gpu installs paddlepaddle-gpu 3.3.1 (CUDA 12.6, from Paddle's own package
#   index) + its bundled CUDA/cuDNN runtime. Target runtime image size: ~4-5.5 GB. Requires
#   the NVIDIA Container Toolkit on the host.
# - The arg is named TORCH_VARIANT (not PADDLE_VARIANT) on purpose: it is reused verbatim
#   across worker/bge_server/paddle_server so the release-images.yml matrix + compose
#   build.args need zero per-service special-casing, even though this service is Paddle not
#   torch.
# - Isolating dependency installation from application code means code-only changes do NOT
#   invalidate this slow dependency layer.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# ── Build-time argument: paddlepaddle variant selector ────────────────────────
# Default is "cpu" — the slim variant. Pass --build-arg TORCH_VARIANT=gpu at build time to
# produce a CUDA-capable image:
#   docker build --build-arg TORCH_VARIANT=gpu -f src/paddle_server/Dockerfile \
#                -t docforge-paddle-server:gpu src
# The two values map to pyproject.toml [project.optional-dependencies] extras (cpu / gpu),
# which steer uv to the correct paddlepaddle wheel index (plain PyPI / paddle-cu126). They are
# declared as conflicting extras so uv rejects any attempt to install both simultaneously.
ARG TORCH_VARIANT=cpu

WORKDIR /workspace

# Tell uv where to place the project virtual environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata only — the dependency layer is rebuilt only when these two files
# change, not when application source code changes.
COPY paddle_server/pyproject.toml paddle_server/uv.lock /workspace/paddle_server/

# Sync the locked production dependencies, activating the selected paddlepaddle variant extra.
# --frozen: fail if uv.lock is out of sync with pyproject.toml (CI safety net).
# --no-dev: omit development-only groups (pytest, ruff, mypy, httpx).
# --no-install-project: the project itself is not a package (package = false in pyproject.toml).
# --extra ${TORCH_VARIANT}: activates either the `cpu` or `gpu` optional-dependency extra.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra "${TORCH_VARIANT}" --project /workspace/paddle_server

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12)
#
# Goal:
# - Contain only what is strictly needed to serve the PP-StructureV3 layout-parsing HTTP API.
# - Expose a clean filesystem:
#     /app/paddle_server -> application source (entrypoint, config_loader, backend/, libs/)
# - Model weights are NOT baked in; they are downloaded on first predict() call from the
#   configured model hoster (PADDLE_PDX_MODEL_SOURCE, default huggingface) and cached under
#   PADDLE_PDX_CACHE_HOME, mounted as a named volume so they persist across restarts.
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# OCI image metadata — declares the image's license + source (GPL-3.0 compliance: the
# full license text lives in the PUBLIC source repo linked here).
LABEL org.opencontainers.image.title="docforge-paddle-server" \
      org.opencontainers.image.description="PaddleOCR PP-StructureV3 micro-service" \
      org.opencontainers.image.source="https://github.com/Florian-BARRE/DocForge" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

# opencv-contrib-python (a paddlex[ocr-core] dependency, non-headless build) dynamically links
# against libGL/libglib/libSM/libXext/libXrender at import time — without these the very first
# `import cv2` (triggered by importing paddleocr) fails with "libGL.so.1: cannot open shared
# object file". libgomp1 is OpenMP's runtime, required by paddlepaddle's CPU math kernels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: suppresses .pyc file creation inside the container.
# - PYTHONUNBUFFERED: log lines appear immediately in stdout/stderr — critical for
#   monitoring model-load/download progress, which can take minutes on first run.
# - PATH: make the uv-built virtual environment the active Python installation without
#   requiring `source /opt/venv/bin/activate`.
# - PADDLE_PDX_CACHE_HOME: PaddleX's model cache root (verified against the paddlex 3.7.0
#   wheel source — see config_loader.py); docker compose mounts a named volume here so every
#   downloaded inference model (layout/OCR/table/formula/seal) persists across restarts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    PADDLE_PDX_CACHE_HOME=/models

# Working directory is set to the application root so that `config_loader`, `backend`, and
# `libs` are all top-level names on sys.path — matches the sibling src/bge_server/ pattern.
# uvicorn targets `entrypoint:app` (a flat module name, not a package path).
WORKDIR /app/paddle_server

# Non-root runtime user (fixed uid/gid). --no-create-home: PADDLE_PDX_CACHE_HOME above is an
# absolute path (/models), not home-relative, so this service needs no home directory of its own.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

# WORKDIR above created /app/paddle_server as root (it predates the COPYs below, so their
# --chown never touches it) — chown the directory itself too, or appuser can read everything
# inside it but can't create NEW entries (e.g. `logs/`) directly under it.
RUN chown appuser:appuser /app/paddle_server

# Pre-create the model cache mount point owned by appuser. docker-compose.yml mounts a named
# volume at /models; Docker seeds a freshly created volume from whatever already exists (content
# + ownership) at its mount target in the image, so a fresh volume comes up appuser-writable
# instead of root-owned — without this, the first predict() call's model download would crash
# with a cache-write PermissionError.
RUN mkdir -p /models && chown appuser:appuser /models

# Copy the prebuilt virtual environment from the builder stage, owned by the runtime user.
# This layer is the largest (paddlepaddle + paddleocr/paddlex + opencv/numpy/pillow) and
# changes only when pyproject.toml / uv.lock change — not on every code edit.
COPY --from=py-build --chown=appuser:appuser /opt/venv /opt/venv

# Copy application source code into the working directory, owned by the runtime user so it can
# create `logs/` under it at runtime if LOGGING_ENABLE_FILE is turned on.
# config_loader.py, entrypoint.py, backend/, and libs/ land directly under /app/paddle_server/
# so they are importable as top-level modules without package qualification.
# This layer is small and rebuilt only when source files change.
COPY --chown=appuser:appuser paddle_server /app/paddle_server

# Drop root for the actual process.
USER appuser

# HTTP port served by uvicorn. Internal-only in prod compose (network alias paddle_server);
# dev republishes it to a host port (see compose/overlays/compose.dev.yml).
EXPOSE 80

# Start the PP-StructureV3 layout-parsing HTTP server.
# - entrypoint:app is the module-level FastAPI app assembled in entrypoint.py.
# - The pipeline loads once in the FastAPI lifespan at startup. First boot may take minutes
#   while models download; subsequent starts reuse the mounted cache volume.
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "80"]
