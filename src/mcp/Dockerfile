# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as context (same context as the main
# docforge image, so both Dockerfiles see the sibling app folders).
# Example:
#   docker build -f src/mcp/Dockerfile -t docforge-mcp:latest src
#
# WORKDIR in the runtime stage is /app/mcp so that `python entrypoint.py` runs with the
# app root as CWD — `import config_loader` and `from libs... import ...` resolve without extra
# PYTHONPATH (config_loader also appends the app root to sys.path defensively).
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create a virtual environment at /opt/venv with only this app's production dependencies.
# - This image stays tiny (httpx + mcp + uvicorn + starlette + config/logging libs) — none of
#   the heavy ML/parsing stack of the main docforge image.
# - Isolate dependency installation from app code for layer-cache efficiency.
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

# Neutral build workspace — paths inside this stage are rooted at /workspace.
WORKDIR /workspace

# Tell uv where to create the project environment; a fixed path is easy to copy to runtime.
# UV_HTTP_TIMEOUT: small buffer over the 30s default in case of slow indexes (no large wheels here).
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=120

# Copy only the lock metadata first so the dependency layer is cached independently of app code.
# Re-resolved only when pyproject.toml or uv.lock changes.
COPY mcp/pyproject.toml mcp/uv.lock /workspace/mcp/

# docforge-sdk is declared as a relative path source (../docforge_sdk from mcp/pyproject.toml),
# so it must exist at /workspace/docforge_sdk — a sibling of /workspace/mcp — before `uv sync` runs.
COPY docforge_sdk /workspace/docforge_sdk

# Install locked production dependencies.
# --frozen: fail if uv.lock is out of sync with pyproject.toml (reproducibility guard).
# --no-dev: skip test/lint/type-check tools.
# --no-editable: build docforge-sdk into a real wheel and install it into the venv instead of an
# editable .pth link — the path source is only marked editable=true for local dev ergonomics, and
# an editable install would point at /workspace/docforge_sdk, a path absent from the runtime stage.
# cache mount: reuse the uv download cache across local rebuilds.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --project /workspace/mcp

###############################################################################
# Stage 2: Runtime image (minimal Python 3.12 slim)
#
# Goal:
# - Contain only what is needed to run the MCP server:
#     /opt/venv          → prebuilt virtual environment
#     /app/mcp  → MCP application source code
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# PYTHONDONTWRITEBYTECODE: no .pyc files written to disk (smaller, immutable runtime).
# PYTHONUNBUFFERED: flush stdout/stderr immediately so `docker logs` shows output in real time.
# PATH: prepend the uv-built venv so its Python + console scripts are used by default.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# Run from the app root so `python entrypoint.py` resolves config_loader + libs without PYTHONPATH.
WORKDIR /app/mcp

# Copy the prebuilt virtual environment from the builder stage (no uv, no build tools in runtime).
COPY --from=py-build /opt/venv /opt/venv

# Copy the MCP application source tree (rebuilt only when app code changes).
COPY mcp /app/mcp

# Expose the internal MCP HTTP port (matched by MCP_PORT and published in docker-compose.yml).
EXPOSE 9000

# Start the MCP server. entrypoint.py dispatches on MCP_TRANSPORT:
#   - streamable-http (container default, set via env) → serves on 0.0.0.0:9000 behind bearer auth
#   - stdio → only used for local runs, not in this container
CMD ["python", "entrypoint.py"]
