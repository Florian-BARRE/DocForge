---
name: dev
description: Start the DocForge dev environment (all services via podman-compose)
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Start Dev Environment

Start all DocForge services in development mode using podman-compose.

## Steps

1. **Check services/.env files exist** — warn if any are missing:
   - `services/docforge/.env`
   - `services/postgres/.env`
   - `services/seaweedfs/.env`
   - `services/redis/.env`

2. **Start services**:
   ```bash
   podman-compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
   ```

3. **Wait for health checks** — poll until PostgreSQL, SeaweedFS, Redis, and Qdrant respond:
   ```bash
   podman-compose ps
   ```

4. **Run Alembic migrations** (if DB just started):
   ```bash
   podman exec -it docforge-app alembic upgrade head
   ```
   Or locally: `cd src/docforge && uv run alembic upgrade head`

5. **Print service URLs**:
   - API:             http://localhost:8000
   - API Docs:        http://localhost:8000/docs
   - SeaweedFS:       http://localhost:8333
   - SeaweedFS Filer: http://localhost:8888
   - Gotenberg:       http://localhost:3000
   - Qdrant UI:       http://localhost:6333/dashboard
   - Redis:           redis://localhost:6379

Report any services that failed to start with their last log lines.
