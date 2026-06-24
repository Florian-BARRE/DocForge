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
# code in src/worker/ (`arq_worker`, `libs.*` = pipeline engine/orchestrator/worker).
# arq_worker.py's path bootstrap registers /app/common and /app/worker on sys.path.
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create /opt/venv with the BASE deps PLUS the optional `worker` group (docling et al.).
# - The dependency contract (pyproject.toml/uv.lock) is shared, in src/common/.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=300

# Shared dependency metadata first (cache layer independent of app code).
COPY docforge/common/pyproject.toml docforge/common/uv.lock /workspace/common/

# Install locked base deps AND the worker extra (docling). --extra worker is THE line
# that makes the worker image large and keeps the backend image small.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra worker --project /workspace/common

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12 slim)
#
# Goal — a clean filesystem:
#     /app/common/   → shared code (config, common_libs)
#     /app/worker/   → worker code (arq_worker, libs = engine/orchestrator/worker)
#     /opt/venv/     → prebuilt virtual environment (base + worker extra)
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# QT_QPA_PLATFORM=offscreen: Docling imports OpenCV, whose Qt plugins need a (headless)
# platform backend. This env is worker-only — the backend image has no OpenCV.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    QT_QPA_PLATFORM=offscreen

# WORKDIR is the worker app root so `arq arq_worker.WorkerSettings` finds arq_worker.py.
# The bootstrap at the top of arq_worker.py adds /app/common and /app/worker to sys.path.
WORKDIR /app/worker

COPY --from=py-build /opt/venv /opt/venv

# Shared code + worker code.
COPY docforge/common /app/common
COPY docforge/worker /app/worker

# Start the arq worker (WorkerSettings class in /app/worker/arq_worker.py).
CMD ["arq", "arq_worker.WorkerSettings"]
