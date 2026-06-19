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

2. **Start services** (build images, run in background):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
   ```

3. **Wait for health checks**:
   ```bash
   docker compose ps
   ```
   Poll until PostgreSQL is `healthy` and the other services are `running`.

4. **Run Alembic migrations** (idempotent):
   ```bash
   docker compose exec -T docforge alembic upgrade head
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
