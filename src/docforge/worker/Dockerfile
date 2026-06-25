# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Worker image for DocForge — runs the arq ingestion pipeline (S0 -> S6).
# Built from the repository root with src/ as context.
# Example:
#   docker build -f src/worker/Dockerfile -t docforge-worker:latest src
#
# This is the HEAVY image: it installs the optional `worker` dependency group
# (docling + its torch/opencv/transformers chain). The backend image deliberately
# omits this group, since only the worker ever runs DoclingBackend.parse().
# No frontend stage — the worker serves no static assets.
#
# Multi-root layout: shared code in src/common/ (`config`, `common_libs.*`), worker
# code in src/worker/ (`entrypoint`, `libs.*` = pipeline engine/orchestrator/worker).
# entrypoint.py's path bootstrap registers /app/common and /app/worker on sys.path.
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create /opt/venv with the BASE deps PLUS the optional `worker` group (docling et al.).
# - The dependency contract (pyproject.toml/uv.lock) is shared, in src/common/.
# - TORCH_VARIANT selects whether Docling uses CPU torch (default, ~2 GB image delta) or
#   CUDA torch (gpu variant, ~8 GB image delta) for GPU-accelerated parsing.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# ── Build-time argument: torch variant selector ───────────────────────────────
# Default is "cpu" — Docling runs on CPU torch (smaller image, works everywhere).
# Pass --build-arg TORCH_VARIANT=gpu to build a CUDA-capable image:
#   docker build --build-arg TORCH_VARIANT=gpu \
#                -f src/docforge/worker/Dockerfile -t docforge-worker:gpu src
# The value is appended to the --extra worker flag so that both the standard worker
# deps AND the correct torch wheel variant are installed in a single uv sync call.
# "cpu" selects cpu-only torch wheels; "gpu" selects the CUDA 12.4 torch wheels
# (mirroring the strategy used by src/bge_server/Dockerfile for its TORCH_VARIANT).
# The two torch variants must be declared as conflicting extras in pyproject.toml so
# that uv never installs both simultaneously.
ARG TORCH_VARIANT=cpu

WORKDIR /workspace

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=300

# Shared dependency metadata first (cache layer independent of app code).
COPY docforge/common/pyproject.toml docforge/common/uv.lock /workspace/common/

# Install locked base deps, the worker extra (docling), and the selected torch variant.
# --extra worker activates Docling and its dependency chain.
# --extra ${TORCH_VARIANT} activates the matching torch wheel index (cpu or cu124).
# The two --extra flags are additive; the conflicting-extras declaration in pyproject.toml
# ensures the cpu and gpu torch variants cannot coexist in the same environment.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra worker --extra "${TORCH_VARIANT}" --project /workspace/common

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12 slim)
#
# Goal — a clean filesystem:
#     /app/common/   → shared code (config, common_libs)
#     /app/worker/   → worker code (entrypoint, libs = engine/orchestrator/worker)
#     /opt/venv/     → prebuilt virtual environment (base + worker extra)
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# QT_QPA_PLATFORM=offscreen: Docling imports OpenCV, whose Qt plugins need a (headless)
# platform backend. This env is worker-only — the backend image has no OpenCV.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    QT_QPA_PLATFORM=offscreen

# WORKDIR is the worker app root so `arq entrypoint.WorkerSettings` finds entrypoint.py.
# The bootstrap at the top of entrypoint.py adds /app/common and /app/worker to sys.path.
WORKDIR /app/worker

COPY --from=py-build /opt/venv /opt/venv

# Shared code + worker code.
COPY docforge/common /app/common
COPY docforge/worker /app/worker

# Start the arq worker (WorkerSettings class in /app/worker/entrypoint.py).
CMD ["arq", "entrypoint.WorkerSettings"]
