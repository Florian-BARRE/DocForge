---
name: compose-file-location
description: docker-compose.rework*.yml files live at the repo root, not under src/docforge-rework/
metadata:
  type: project
---

`docker-compose.rework.yml`, `docker-compose.rework.dev.yml`, `docker-compose.rework.gpu.yml` all live
at `/home/dev-center/projects/docforge/` (repo root), alongside the frozen legacy `docker-compose.yml` /
`docker-compose.dev.yml` / `docker-compose.gpu.yml`. `services/docforge-rework/`, `services/bge_server/`,
etc. are also repo-root-relative.

**Why:** this agent's default cwd is `src/docforge-rework/` (the app-only tree) — an `ls` there will
show none of the compose/env files and can mislead into thinking they're missing.

**How to apply:** always resolve compose/env/service paths from the repo root
(`/home/dev-center/projects/docforge/`), not from cwd. Dockerfiles themselves (`app/Dockerfile`,
`worker/Dockerfile`) do live under `src/docforge-rework/`.
