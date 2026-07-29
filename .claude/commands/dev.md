---
name: dev
description: Start the DocForge dev environment (all services via docker compose) with hot reload
user-invocable: true
allowed-tools: "Bash(*), Read(*)"
---

# Start Dev Environment

Start all DocForge services in development mode using `docker compose` (v2). Backend (uvicorn) and
frontend (Vite) run with hot reload; `app/` and `shared/` are volume-mounted, `worker/` is baked
(a worker change needs a rebuild).

## Steps

1. **Check env files exist** — warn if any are missing (copy from the `.example` templates):
   - `services/docforge-rework/.env`
   - `services/docforge-rework/postgres.env`
   - `services/docforge-rework/s3_config.json`
   - `services/bge_server/.env`

2. **Start the full stack** (`--profile full` is **mandatory** — app/worker/frontend are gated
   behind it; without it only the stores start and the compose rejects the frontend dependency):
   ```bash
   docker compose -f docker-compose.rework.yml -f docker-compose.rework.dev.yml --profile full up --build -d
   ```
   - GPU host (NVIDIA + Container Toolkit): add `-f docker-compose.rework.gpu.yml` to run
     `bge_server` + `worker` on GPU.
   - No `--build` needed after the first build for `app`/`shared` changes (mounted); rebuild the
     `worker` image when its code or dependencies change.

3. **Wait for health**:
   ```bash
   docker compose -f docker-compose.rework.yml ps
   ```
   Poll until postgres/redis/qdrant/seaweedfs are `healthy`.

4. **Run Alembic migrations** (idempotent; env.py is async on asyncpg):
   ```bash
   docker compose -f docker-compose.rework.yml exec rework_app \
     sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
   ```

5. **Print service URLs**:
   - Frontend (Vite HMR): http://localhost:10046
   - API + Scalar docs:   http://localhost:10040/scalar
   - Qdrant:              http://localhost:10043/dashboard
   - SeaweedFS S3:        http://localhost:10044
   - PostgreSQL:          localhost:10041 (user/db: docforge)
   - bge_server health:   http://localhost:10047/health

Report any service that failed to start with its last log lines:
```bash
docker compose -f docker-compose.rework.yml logs --tail=50 <service>
```
