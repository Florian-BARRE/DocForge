---
paths:
  - "Dockerfile"
  - "**/Dockerfile"
  - "docker-compose*.yml"
---

# Container Project Rules — Podman

> **CRITICAL:** This project uses **Podman + podman-compose**. Never write `docker` or
> `docker-compose` anywhere — not in Dockerfiles, compose files, shell commands, or comments.
> Docker is not available in this environment.

---

## General Principles

- Python projects always use **uv** for dependency resolution — never pip directly in Dockerfiles.
- React frontend builds happen in a dedicated stage; only the compiled `dist/` bundle is copied into the runtime image.
- Every Dockerfile must be **fully commented in English**, explaining each stage's goal, each `ENV`, each `COPY`, and each `RUN` command. No silent instructions.
- Always use **multi-stage builds** to keep runtime images minimal.
- Runtime images contain only what is strictly necessary to run the service — no build tools, no dev dependencies.
- All CLI examples use `podman build` and `podman-compose`, never `docker build` or `docker-compose`.

---

## Project Structure — Combined Layouts

When Podman is used, the application source tree (as defined in python.md or fastapi.md) lives inside `src/<app_name>/`. The repository root holds only orchestration files.

### Python-only + Podman

```
project_root/
├── src/
│   └── myapp/                     # Application source (python.md layout)
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── main.py                # Entry point
│       ├── config/
│       │   ├── __init__.py
│       │   └── runtime/
│       │       └── runtime_config.py
│       └── libs/
│           └── <module>/
├── services/
│   └── myapp/
│       └── .env
├── docker-compose.yml             # Podman-compatible compose file
└── docker-compose.dev.yml
```

### FastAPI + Podman (with frontend)

```
project_root/
├── src/
│   └── myapp/                     # Application source (fastapi.md layout)
│       ├── Dockerfile
│       ├── pyproject.toml
│       ├── uv.lock
│       ├── entrypoint.py          # FastAPI entry point
│       ├── config/
│       │   ├── __init__.py
│       │   └── runtime/
│       │       └── runtime_config.py
│       ├── libs/                  # Shared domain modules
│       │   └── <module>/
│       ├── backend/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── context.py
│       │   ├── lifespan.py
│       │   ├── routers/
│       │   └── libs/              # Backend-specific utilities
│       │       └── utils/
│       └── frontend/
│           ├── package.json
│           ├── package-lock.json
│           ├── vite.config.ts
│           └── src/
├── services/
│   ├── myapp/
│   │   └── .env
│   └── postgres/
│       └── .env
├── docker-compose.yml
└── docker-compose.dev.yml
```

### Multi-container project

```
project_root/
├── src/
│   ├── app1/               # App 1 source + Dockerfile
│   └── app2/               # App 2 source + Dockerfile
├── services/
│   ├── app1/
│   │   └── .env
│   ├── app2/
│   │   └── .env
│   └── postgres/           # Third-party services (DB, cache, etc.)
│       └── .env
├── docker-compose.yml
└── docker-compose.dev.yml
```

Rules:
- Third-party services (PostgreSQL, Redis, etc.) that use official images without a custom Dockerfile get their own folder under `services/` with a `.env` file if needed.
- Each app's `.env` file lives under `services/<app_name>/` — never at the project root.
- Dockerfiles live inside the app's source folder (`src/<app_name>/Dockerfile`), not at the project root.

---

## Dockerfile Structure

> Dockerfiles are Podman-compatible out of the box — no changes needed to the Dockerfile syntax.
> The difference is in how you build and run them: always use `podman build` and `podman-compose`.

### Python-only project (two stages)

```dockerfile
# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as context.
# Example (Podman):
#   podman build -f src/myapp/Dockerfile -t myapp:latest src
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Create a virtual environment at /opt/venv
# - Install only locked production dependencies from uv.lock
# - Cache dependency layer separately from application code
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

# Tell uv where to create the project environment.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata first to maximize layer cache reuse.
# Dependency layers are only rebuilt when pyproject.toml or uv.lock changes.
COPY myapp/pyproject.toml myapp/uv.lock /workspace/myapp/

# Install locked production dependencies.
# --frozen: fail if lock file is out of sync with pyproject.toml.
# --no-dev: skip development dependencies.
# cache mount: speeds up repeated local builds without network round-trips.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project /workspace/myapp

###############################################################################
# Stage 2: Runtime image (minimal Python runtime)
#
# Goal:
# - Contain only what is needed to run the service
# - Expose a clean filesystem:
#     /app/myapp  -> application source code
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

# Runtime best practices:
# - PYTHONDONTWRITEBYTECODE: no .pyc files written to disk
# - PYTHONUNBUFFERED: logs appear immediately in stdout/stderr
# - PATH: make the uv-built venv the active Python environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Copy prebuilt virtual environment from the builder stage.
COPY --from=py-build /opt/venv /opt/venv

# Copy application source code only.
COPY myapp /app/myapp

EXPOSE 8000

# Start the FastAPI application via uvicorn.
CMD ["uvicorn", "myapp.entrypoint:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Python + React fullstack project (three stages)

```dockerfile
# syntax=docker/dockerfile:1.7

###############################################################################
# Build note:
# Built from the repository root with the src/ directory as context.
# Example (Podman):
#   podman build -f src/myapp/Dockerfile -t myapp:latest src
###############################################################################

###############################################################################
# Stage 1: Python dependency builder (uv + Python 3.12)
#
# Goal:
# - Install locked production Python dependencies into /opt/venv
# - Isolate dependency installation from application code for cache efficiency
###############################################################################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS py-build

WORKDIR /workspace

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Copy lock metadata first — dependency cache is invalidated only when these change.
COPY myapp/pyproject.toml myapp/uv.lock /workspace/myapp/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --project /workspace/myapp

###############################################################################
# Stage 2: Frontend builder (Node + Vite)
#
# Goal:
# - Install Node dependencies reproducibly with npm ci
# - Build the optimized production bundle into frontend/dist
###############################################################################
FROM node:22-bookworm-slim AS ui-build

WORKDIR /workspace/myapp/frontend

# Copy package descriptors first to enable npm dependency-layer caching.
COPY myapp/frontend/package.json myapp/frontend/package-lock.json ./

# Reproducible install strictly from package-lock.json.
RUN npm ci

# Copy frontend source and compile production bundle.
COPY myapp/frontend/ ./
RUN npm run build

###############################################################################
# Stage 3: Runtime image (minimal Python runtime)
#
# Goal:
# - Contain only what is needed to run the service
# - Expose a clean filesystem:
#     /app/myapp              -> backend application code
#     /app/myapp/frontend/dist -> compiled frontend bundle served as static files
###############################################################################
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# Copy prebuilt virtual environment from Python build stage.
COPY --from=py-build /opt/venv /opt/venv

# Copy backend application source code.
COPY myapp /app/myapp

# Copy compiled frontend bundle into the backend tree.
# FastAPI mounts this directory as static files at the root URL.
COPY --from=ui-build /workspace/myapp/frontend/dist /app/myapp/frontend/dist

EXPOSE 8000

CMD ["uvicorn", "myapp.entrypoint:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## `docker-compose.yml` — Production (Podman-compatible)

Standard production compose file. Podman-compose reads this format without modification.
All services declared, volumes and networks explicitly named, env files referenced from `services/`.

```yaml
services:
  myapp:
    build:
      context: src               # Build context is the src/ directory
      dockerfile: myapp/Dockerfile
    image: myapp:latest
    ports:
      - "8000:8000"
    env_file:
      - services/myapp/.env
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  postgres:
    image: postgres:16-bookworm
    env_file:
      - services/postgres/.env
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

volumes:
  postgres_data:
```

Start with Podman:
```bash
# Production
podman-compose -f docker-compose.yml up -d

# Development
podman-compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
```

---

## `docker-compose.dev.yml` — Development

The dev compose file extends or overrides the production one to enable real-time development
inside containers. It uses **volume mounts** for source code and enables **hot reload**.

```yaml
# Development overrides — use with:
#   podman-compose -f docker-compose.yml -f docker-compose.dev.yml up

services:
  myapp:
    build:
      context: src
      dockerfile: myapp/Dockerfile
      # Build the full image even in dev so dependencies are resolved correctly.
      # Source code is then overlaid by the volume mount below.
    volumes:
      # Mount source code directly into the container so edits are reflected immediately.
      - ./src/myapp:/app/myapp
    environment:
      # Enable uvicorn hot reload in development.
      - DEV_MODE=true
    command: >
      uvicorn myapp.entrypoint:app
      --host 0.0.0.0
      --port 8000
      --reload
      --reload-dir /app/myapp
```

Rules:
- The dev compose file **never duplicates** the full service definition — only overrides what differs.
- Source code directories are mounted as volumes so edits are reflected without rebuilding.
- `--reload` is only present in the dev command, never in the production `CMD`.
- Hot reload is enabled for: uvicorn (`--reload`), Vite dev server (`vite --host`). If a React
  frontend needs live reload in dev, run the Vite dev server as a separate service in
  `docker-compose.dev.yml` rather than serving the static build.
- Environment variable `DEV_MODE=true` activates the early debug logger in `runtime_config.py`.

---

## Dockerfile Commenting Rules

Every Dockerfile instruction must be accompanied by a comment that explains **why**, not just what:

- The purpose of each `FROM` stage (stated as a `# Goal:` block).
- Every `ENV` variable and what it controls.
- Every `COPY` and what it enables (cache optimization, layer separation, etc.).
- Every `RUN` command and its flags.
- The `EXPOSE` port and which service uses it.
- The `CMD` and the module path it targets.

A reader who has never seen the project should understand the full build process from the Dockerfile alone.
