# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as context.
# Example:
#   docker build -f src/bge_m3_server/Dockerfile -t bge-m3-server:latest src
###############################################################################

###############################################################################
# Single-stage runtime image (CPU).
#
# Goal:
# - Serve BAAI/bge-m3 (dense + native multilingual sparse) over a TEI-compatible HTTP API.
# - Keep the image CPU-only: torch is installed from the CPU wheel index (no CUDA payload).
#
# The model weights are NOT baked in; they are pulled on first start and cached in a volume
# (HF_HOME), so the image stays small and the model can be swapped via env without a rebuild.
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: no .pyc files on disk
# - PYTHONUNBUFFERED: logs appear immediately in stdout/stderr
# - HF_HOME: HuggingFace cache location (mounted as a volume so weights persist)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models

WORKDIR /app

# Install uv (the project-standard resolver) from its official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies. Torch is pulled from the CPU wheel index first so FlagEmbedding
# resolves against the CPU build (no CUDA). The cache mount speeds up repeated local builds.
COPY embedding_server/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-cache torch --index-url https://download.pytorch.org/whl/cpu \
 && uv pip install --system --no-cache -r /app/requirements.txt

# Copy the service code only (small, changes often — kept after the dependency layer for cache reuse).
COPY embedding_server/app.py /app/app.py

# HTTP port served by uvicorn — TEI parity is the API shape, not the port (set freely in compose).
EXPOSE 80

# Start the embedding server. The model loads once in the FastAPI lifespan on startup.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
