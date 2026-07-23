---
name: v1-audit-open-gaps
description: unresolved infra gaps found in the 2026-07-24 read-only V1 audit of the rework stack — check off as fixed, don't re-discover from scratch
metadata:
  type: project
---

Read-only orchestration audit run 2026-07-24 against the then-live stack (up 9 days, ports
10040-10047 all healthy). Items 1-4 + the CORS nit were fixed 2026-07-24 (compose/Dockerfile/env edits
only, live stack left untouched — no build/up/restart run as part of the fix; a real prod `--build` to
exercise the new `ui-build` stage is a separate follow-up). Re-verify before assuming any of the
remaining items are resolved — check the actual file, this list decays:

1. ~~**`app/Dockerfile` has no frontend `ui-build` stage**~~ — FIXED. Added a `node:22-bookworm-slim`
   `ui-build` stage (`npm ci && npm run build` in `app/frontend`) between py-build and runtime; runtime
   now does `COPY --from=ui-build /workspace/frontend/dist /app/app/frontend/dist` instead of relying on
   a host-built `dist/` riding along in `COPY app /app/app`.
2. ~~**DNS pin gap**~~ — FIXED. `dns: [1.1.1.1, 8.8.8.8]` added to `rework_frontend`
   (`docker-compose.rework.dev.yml`) and `rework_bge_server` (`docker-compose.rework.yml`), matching
   app/worker. See [[dns-resolver-baked-at-creation]] for why this pin matters even when a service
   "currently" resolves fine.
3. **No SeaweedFS bucket bootstrap** — still open. `S3Client` never calls create-bucket; a fresh
   `rework_seaweedfs_data` volume has no bucket and every upload 404s until someone creates it by hand.
   Deliberately NOT infra's fix — being handled in application code by another agent (no init container
   wanted here).
4. ~~**No persistent HF/docling model cache in prod**~~ — FIXED. Named volume `rework_worker_hf_cache`
   mounted at `/root/.cache/huggingface` on `rework_worker` in the base `docker-compose.rework.yml`,
   declared under top-level `volumes:` (mirrors `rework_bge_models`). Note: in the dev-layered config
   this mount is fully superseded by the dev override's host-cache bind at the same target — compose
   replaces a service's `volumes:` list wholesale on override, it doesn't merge by target — so the named
   volume is prod-only in practice, which is the intended behavior.
5. **`qdrant/qdrant:latest` and `chrislusf/seaweedfs:latest`** unpinned — still open, deliberately
   deferred (needs the running version to pin against; upgrade risk not infra's call alone).
6. **`services/docforge-rework/s3_config.json` git-tracked with a real secret** — still open,
   deliberately deferred (changes the setup flow, owned by whoever owns onboarding docs).
7. **Partial healthcheck/depends_on gating** — still open (`rework_redis`/`qdrant`/`seaweedfs`/
   `gotenberg` have no healthcheck; worker depends on seaweedfs only at `service_started`). Confirmed
   low practical impact — no eager connection at boot for any of app/worker.
8. **No resource limits** on app/worker/postgres/qdrant — still open, deliberately deferred (needs VM
   capacity numbers).

~~Nit: `FASTAPI_CORS_ALLOWED_ORIGINS` listed dead `http://localhost:5173`~~ — FIXED (dropped from both
`services/docforge-rework/.env` and the tracked `.env.example`; `10046` was already present and is the
actual dev-frontend host port).

Still open / not worth a fix cycle: no Dockerfile sets a non-root `USER`; `psycopg2-binary` (Alembic
offline `--sql` mode only) lives in the `dev` group and is absent from runtime images — harmless since
only `alembic upgrade head` runs in-container per CLAUDE.md.
