# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as build context.
# Example:
#   docker build --build-arg TORCH_VARIANT=gpu -f src/mineru_server/Dockerfile \
#                -t docforge-mineru-server:gpu src
#
# GPU-ONLY SERVICE: MinerU2.5-Pro's VLM backend REQUIRES CUDA. The default `cpu` variant exists only
# to build/import-test the wiring on a CPU host — it CANNOT actually parse (the model needs a GPU),
# and the service reports /health UNHEALTHY on a CPU host. Ship the `gpu` variant to production.
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Sync the locked production dependencies from uv.lock into a virtual environment at /opt/venv,
#   selecting the correct mineru+torch wheel variant via TORCH_VARIANT.
# - TORCH_VARIANT=cpu  (default) installs mineru[core] + torch CPU (wiring build-test only).
# - TORCH_VARIANT=gpu installs mineru[core] + torch 2.x+cu126 (CUDA 12.6 — REQUIRED for the Tesla
#   V100 sm_70 prod GPU; cu129/cu130 drop Volta kernels) + the CUDA runtime libs. Target runtime image
#   size: multi-GiB. Requires the NVIDIA Container Toolkit on the host.
# - The arg is named TORCH_VARIANT (same as worker/bge_server/paddle_server) so the release-images.yml
#   matrix + compose build.args need zero per-service special-casing.
# - Isolating dependency installation from application code means code-only changes do NOT invalidate
#   this slow dependency layer.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# ── Build-time argument: mineru+torch variant selector ────────────────────────
# Default is "cpu" (wiring build-test). Pass --build-arg TORCH_VARIANT=gpu at build time to produce
# the CUDA-capable production image. The two values map to pyproject.toml
# [project.optional-dependencies] extras (cpu / gpu), which steer uv to the correct torch wheel index
# (pytorch-cpu / pytorch-cu126). They are declared as conflicting extras so uv rejects installing both.
ARG TORCH_VARIANT=cpu

WORKDIR /workspace

# Tell uv where to place the project virtual environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata only — the dependency layer is rebuilt only when these two files change, not when
# application source code changes.
COPY mineru_server/pyproject.toml mineru_server/uv.lock /workspace/mineru_server/

# Sync the locked production dependencies, activating the selected mineru+torch variant extra.
# --frozen: fail if uv.lock is out of sync with pyproject.toml (CI safety net).
# --no-dev: omit development-only groups (pytest, ruff, mypy, httpx).
# --no-install-project: the project itself is not a package (package = false in pyproject.toml).
# --extra ${TORCH_VARIANT}: activates either the `cpu` or `gpu` optional-dependency extra, which gates
#   the correct torch wheel + mineru[core]. The two extras are mutually exclusive (conflicting).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra "${TORCH_VARIANT}" --project /workspace/mineru_server

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12)
#
# Goal:
# - Contain only what is strictly needed to serve the MinerU2.5-Pro VLM parse HTTP API.
# - Expose a clean filesystem:
#     /app/mineru_server -> application source (entrypoint, config_loader, backend/, libs/)
# - Model weights are NOT baked in; they are downloaded on the first /parse call from the configured
#   model hoster (MINERU_MODEL_SOURCE, default huggingface) and cached under MINERU_MODEL_CACHE_HOME,
#   mounted as a named volume so they persist across restarts.
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# OCI image metadata — declares the image's license + source (GPL-3.0 compliance: the full license
# text lives in the PUBLIC source repo linked here).
LABEL org.opencontainers.image.title="docforge-mineru-server" \
      org.opencontainers.image.description="MinerU2.5-Pro VLM layout-parsing micro-service" \
      org.opencontainers.image.source="https://github.com/Florian-BARRE/DocForge" \
      org.opencontainers.image.licenses="GPL-3.0-or-later"

# libgomp1 is OpenMP's runtime (torch CPU math kernels). The X11/GL libs are required by MinerU's
# OpenCV/PDF-rendering dependency chain, which dynamically links libGL/libSM/... at import (same class
# of requirement as paddle_server's opencv X11 libs).
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
# - PYTHONUNBUFFERED: log lines appear immediately in stdout/stderr — critical for monitoring
#   model-load/download progress, which can take minutes on first run.
# - PATH: make the uv-built virtual environment the active Python installation.
# - HF_HOME / MINERU_MODEL_CACHE_HOME: MinerU caches its downloaded VLM weights here; docker compose
#   mounts a named volume so weights persist across restarts.
# - MALLOC_ARENA_MAX: caps glibc malloc arenas at 2 — the multi-threaded native stack (torch/OpenMP)
#   otherwise scales arenas to the HOST's core count, inflating RSS well past what is needed.
# - TORCH_DISABLE_NATIVE_JIT: torch>=2.10's `torch/_native` eager-triton router (see
#   torch/_native/triton_utils.py::register_op_override, gated by
#   torch/_native/common_utils.py::check_native_jit_disabled) opportunistically overrides SOME eager
#   ops (observed: the "bmm" op family — e.g. the rotary-embedding matmul in transformers' Qwen2-VL
#   forward pass, MinerU's VLM backend) with a Triton kernel that is JIT-COMPILED AT RUNTIME on first
#   call. That JIT compile needs a host C compiler (gcc/cc), which this slim runtime image does not
#   ship, so the very first GPU parse crashes with "RuntimeError: Failed to find C compiler." This var
#   makes `register_op_override` a documented no-op (verified: `get_dsl_operations("triton")` returns
#   `["bmm"]` unset vs `[]` set, on the SAME torch==2.13.0+cu126/triton==3.7.1 pair mineru ships) —
#   eager execution then falls straight through to the standard ATen/cuBLAS bmm kernel, exactly as
#   torch<2.10 always did (verified: torch==2.9.0, which bge_server/worker/dots_ocr_server precedents
#   don't hit this on, has no `torch/_native/` package at all). No image bloat, no torch downgrade, no
#   runtime JIT latency. See agent-memory/infra/mineru-torch-native-triton-jit.md.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/models \
    MINERU_MODEL_CACHE_HOME=/models \
    MALLOC_ARENA_MAX=2 \
    TORCH_DISABLE_NATIVE_JIT=1

# Working directory is set to the application root so that `config_loader`, `backend`, and `libs` are
# all top-level names on sys.path — matches the sibling src/bge_server/ + src/paddle_server/ pattern.
# uvicorn targets `entrypoint:app` (a flat module name, not a package path).
WORKDIR /app/mineru_server

# Non-root runtime user (fixed uid/gid). --no-create-home: MINERU_MODEL_CACHE_HOME above is an
# absolute path (/models), not home-relative, so this service needs no home directory of its own.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

# WORKDIR above created /app/mineru_server as root — chown it so appuser can create NEW entries
# (e.g. `logs/`) directly under it.
RUN chown appuser:appuser /app/mineru_server

# Pre-create the model cache mount point owned by appuser. docker compose mounts a named volume at
# /models; a fresh volume is seeded from the mount target's ownership in the image, so this makes the
# first-parse weights download appuser-writable instead of crashing with a cache-write PermissionError.
RUN mkdir -p /models && chown appuser:appuser /models

# Copy the prebuilt virtual environment from the builder stage, owned by the runtime user. This layer
# is the largest (mineru + torch + transformers) and changes only when pyproject.toml / uv.lock change.
COPY --from=py-build --chown=appuser:appuser /opt/venv /opt/venv

# Copy application source code into the working directory, owned by the runtime user so it can create
# `logs/` under it at runtime if LOGGING_ENABLE_FILE is turned on. config_loader.py, entrypoint.py,
# backend/, and libs/ land directly under /app/mineru_server/ so they are importable as top-level
# modules without package qualification. This layer is small and rebuilt only when source changes.
COPY --chown=appuser:appuser mineru_server /app/mineru_server

# Drop root for the actual process.
USER appuser

# HTTP port served by uvicorn. Internal-only in prod compose (network alias mineru_server); dev
# republishes it to a host port (see compose/overlays/compose.dev.yml).
EXPOSE 80

# Start the MinerU2.5-Pro VLM parse HTTP server.
# - entrypoint:app is the module-level FastAPI app assembled in entrypoint.py.
# - The MinerU VLM model loads LAZILY on the first /parse request (not at startup); first parse may
#   take minutes while weights download, then subsequent parses reuse the mounted cache volume.
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "80"]
