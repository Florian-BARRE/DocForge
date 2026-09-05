# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as build context.
# Example:
#   docker build -f src/bge_server/Dockerfile -t docforge-bge-server:latest src
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Sync the locked production dependencies from uv.lock into a virtual environment
#   at /opt/venv, selecting the correct torch wheel variant via TORCH_VARIANT.
# - TORCH_VARIANT=cpu  (default) installs torch 2.13.0+cpu (~200 MB) — no nvidia-* libs.
#   Target runtime image size: ~2 GB.
# - TORCH_VARIANT=gpu installs torch 2.11.0+cu128 (~2 GB) + all nvidia-cu12-* runtime libs.
#   Target runtime image size: ~8.5 GB. Requires NVIDIA Container Toolkit on the host.
# - Isolating dependency installation from application code means code-only changes do
#   NOT invalidate this slow dependency layer.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# ── Build-time argument: torch variant selector ───────────────────────────────
# Default is "cpu" — the slim variant. Pass --build-arg TORCH_VARIANT=gpu at build time
# to produce a CUDA-capable image:
#   docker build --build-arg TORCH_VARIANT=gpu -f src/bge_server/Dockerfile \
#                -t docforge-bge-server:gpu src
# The two values map to pyproject.toml [project.optional-dependencies] extras (cpu / gpu),
# which steer uv to the correct torch wheel index (pytorch-cpu / pytorch-cu128). They are
# declared as conflicting extras so uv rejects any attempt to install both simultaneously.
ARG TORCH_VARIANT=cpu

WORKDIR /workspace

# Tell uv where to place the project virtual environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata only — the dependency layer is rebuilt only when these two files
# change, not when application source code changes.
COPY bge_server/pyproject.toml bge_server/uv.lock /workspace/bge_server/

# Sync the locked production dependencies, activating the selected torch variant extra.
# --frozen: fail if uv.lock is out of sync with pyproject.toml (CI safety net).
# --no-dev: omit development-only groups (pytest, ruff, mypy, httpx).
# --no-install-project: the project itself is not a package (package = false in pyproject.toml).
# --extra ${TORCH_VARIANT}: activates either the `cpu` or `gpu` optional-dependency extra,
#   which gates the correct torch wheel + (for gpu) all nvidia-cu12-* runtime libs.
#   The two extras are mutually exclusive (declared as conflicting in pyproject.toml).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --extra "${TORCH_VARIANT}" --project /workspace/bge_server

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12)
#
# Goal:
# - Contain only what is strictly needed to serve the BGE model-suite HTTP API.
# - Expose a clean filesystem:
#     /app/bge_server -> application source (entrypoint, config_loader, backend/, libs/)
# - Model weights are NOT baked in; they are downloaded on first start from HuggingFace
#   and cached in a named volume (HF_HOME=/models) so they persist across container
#   restarts and never need re-downloading.
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: suppresses .pyc file creation inside the container.
# - PYTHONUNBUFFERED: log lines appear immediately in stdout/stderr — critical for
#   monitoring model-load progress, which can take minutes on first run.
# - PATH: make the uv-built virtual environment the active Python installation without
#   requiring `source /opt/venv/bin/activate`.
# - HF_HOME: HuggingFace cache directory; docker compose mounts a named volume here so
#   BGE-M3 and BGE-reranker-v2-m3 weights (~4.4 GiB total) persist across restarts.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    HF_HOME=/models

# Working directory is set to the application root so that `config_loader`, `backend`,
# and `libs` are all top-level names on sys.path — matching the pattern of the sibling
# src/mcp/ service. uvicorn targets `entrypoint:app` (a flat module name, not a package path).
WORKDIR /app/bge_server

# Non-root runtime user (fixed uid/gid). --no-create-home: HF_HOME above is an absolute path
# (/models), not home-relative, so this service needs no home directory of its own.
RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

# WORKDIR above created /app/bge_server as root (it predates the COPYs below, so their --chown
# never touches it) — chown the directory itself too, or appuser can read everything inside it
# but can't create NEW entries (e.g. `logs/`) directly under it.
RUN chown appuser:appuser /app/bge_server

# Pre-create the HF cache mount point owned by appuser. docker-compose.yml mounts a named volume
# at /models; Docker seeds a freshly created volume from whatever already exists (content +
# ownership) at its mount target in the image, so a fresh volume comes up appuser-writable
# instead of root-owned — without this, the first-boot weights download would crash with a
# cache-write PermissionError.
RUN mkdir -p /models && chown appuser:appuser /models

# Copy the prebuilt virtual environment from the builder stage, owned by the runtime user.
# This layer is the largest (~500 MB for CPU torch + FlagEmbedding) and changes only
# when pyproject.toml / uv.lock change — not on every code edit.
COPY --from=py-build --chown=appuser:appuser /opt/venv /opt/venv

# Copy application source code into the working directory, owned by the runtime user so it can
# create `logs/` under it at runtime if LOGGING_ENABLE_FILE is turned on.
# config_loader.py, entrypoint.py, backend/, and libs/ land directly under /app/bge_server/
# so they are importable as top-level modules without package qualification.
# This layer is small and rebuilt only when source files change.
COPY --chown=appuser:appuser bge_server /app/bge_server

# Drop root for the actual process.
USER appuser

# HTTP port served by uvicorn. TEI parity is the API shape, not the port — docker compose
# maps this internal port 80 to host port 10026 (see docker-compose.yml).
EXPOSE 80

# Start the BGE model-suite HTTP server.
# - entrypoint:app is the module-level FastAPI app assembled in entrypoint.py.
# - Both BGE models (embed + reranker) load once in the FastAPI lifespan at startup.
#   First boot may take 30-120 s while weights download; subsequent starts use the volume.
CMD ["uvicorn", "entrypoint:app", "--host", "0.0.0.0", "--port", "80"]
