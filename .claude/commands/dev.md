---
name: dev
description: Start the DocForge dev environment (all services via docker compose) with hot reload
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Start Dev Environment

Start all DocForge services in development mode using `docker compose` (v2). Backend
(uvicorn) and frontend (Vite) both run with hot reload.

## Steps

1. **Check services/.env files exist** — warn if any are missing:
   - `services/docforge/.env`
   - `services/postgres/.env`
   - `services/redis/.env`
   - `services/gotenberg/.env`

2. **Start services** (run in background, GPU by default on this host):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d
   ```
   This host has an NVIDIA GPU + Container Toolkit, so dev runs `bge_server` (BGE-M3 embed/rerank)
   and `worker` (Docling) on **GPU** via `docker-compose.gpu.yml` — embedding is ~25× faster than
   CPU (≈2 s vs ≈45 s for a batch), which matters for the S6 embed timeout on real documents.
   - No `--build`: dev mounts source as volumes, so code changes are picked up live; the `:gpu`
     images already exist. Rebuild only when **dependencies** change:
     `docker compose -f docker-compose.yml -f docker-compose.gpu.yml build bge_server worker`
     (~15-20 min first time; ~9.5 GB images).
   - **CPU fallback** (no GPU host / toolkit absent): drop the gpu layer →
     `docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d`.
   - Verify GPU is live: `docker compose exec -T bge_server python -c "import torch;print(torch.cuda.is_available())"` → `True`.

3. **Wait for health checks**:
   ```bash
   docker compose ps
   ```
   Poll until PostgreSQL is `healthy` and the other services are `running`.

4. **Run Alembic migrations** (idempotent). Migrations live in `common/` now, so run them
   from `/app/common`:
   ```bash
   docker compose exec -T docforge sh -c 'cd /app/common && alembic upgrade head'
   ```

5. **Print service URLs**:
   - Frontend (Vite HMR): http://localhost:10023
   - API:                http://localhost:10020
   - API Docs:           http://localhost:10020/docs
   - SeaweedFS S3:       http://localhost:10021
   - SeaweedFS master:   http://localhost:10022
   - Qdrant:             http://localhost:10025/dashboard
   - PostgreSQL:         localhost:10024 (user/db: docforge)
   - Redis:              internal docforge_net only

Report any services that failed to start with their last log lines:
```bash
docker compose logs --tail=50 <service>
```
