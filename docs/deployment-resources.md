# DocForge — Resource Footprint & Limits

How much CPU/RAM each service consumes, the per-service limits enforced in
`docker-compose.yml`, and how to monitor and tune them.

> **TL;DR** — Every service declares `deploy.resources.limits` (cpus + memory).
> These are **hard ceilings, not reservations**: a container uses only what it
> needs, but can never run away and saturate the host. They keep the stack
> "sober" by default and prevent the memory pressure that destabilises the
> Docker Desktop / WSL2 engine.

---

## 1. Host & engine context

On the reference dev machine:

| Layer | Capacity |
|---|---|
| Physical host RAM | ~31.7 GiB |
| Docker Desktop WSL2 VM (what containers actually share) | **~15.5 GiB** |

The WSL2 VM cap — not the physical RAM — is the real budget. When uncapped
services (worker + ML inference during ingestion) overshoot it, the VM thrashes
and the Linux engine starts returning `500 Internal Server Error` (port-proxy
flaps, `docker` commands fail intermittently). Capping each service keeps the
realistic concurrent peak well under the VM ceiling.

The WSL2 VM memory can be raised in `%UserProfile%\.wslconfig`:

```ini
[wsl2]
memory=20GB
```

…but that works against the "stay sober" goal. The limits below are the
preferred compromise.

---

## 2. Per-service limits

Limits live in `docker-compose.yml` (`deploy.resources.limits`) for the 11
production services, and in `docker-compose.dev.yml` for the dev-only
`frontend`. They are honoured by `docker compose up` in Compose v2 — **no swarm
required** — and apply identically in production and dev.

| Service | RAM ceiling | CPU ceiling | Tier / rationale |
|---|---|---|---|
| **worker** (arq) | 4 GiB | 4 | Heaviest: Docling parsing + full S0→S6 pipeline. Largest budget so ingestion stays workable. |
| **tei** (BGE-M3 embed) | 3 GiB | 3 | CPU-bound embedding inference; model is memory-mapped. |
| **reranker** (BGE-reranker-v2-m3) | 3 GiB | 3 | Cross-encoder ~2.1 GiB resident + batch scoring. |
| **docforge** (FastAPI API) | 2 GiB | 2 | I/O-bound at runtime; embeds delegated to TEI. |
| **gotenberg** | 2 GiB | 2 | LibreOffice + Chromium spike during conversion. |
| **qdrant** | 2 GiB | 2 | Vector index/search; grows with collection size. |
| **postgres** | 1 GiB | 1 | Catalogue + job store; small footprint. |
| **seaweedfs** | 1 GiB | 1 | Object gateway; light steady-state. |
| **frontend** (Vite dev, dev only) | 1 GiB | 1 | Node dev server with HMR. |
| **redis** | 512 MiB | 1 | arq queue broker; tiny resident set. |
| **mcp** | 512 MiB | 1 | Thin HTTP proxy to the API. |
| **pgadmin** | 512 MiB | 1 | Inspection UI; off the hot path. |

**Sum of ceilings ≈ 21 GiB**, which is intentionally larger than the 15.5 GiB
VM: limits are ceilings, not reservations, so they never all peak at once. The
realistic concurrent peak during ingestion (worker + tei + qdrant + postgres +
docforge + a converter burst) stays comfortably below the VM cap.

---

## 3. Observed consumption (idle snapshot)

Captured with `docker stats --no-stream` on an idle stack (no active ingestion):

| Service | Mem (idle) | CPU (idle) | Note |
|---|---|---|---|
| reranker | ~2.15 GiB | ~21% | Model resident in RAM — the largest idle consumer. |
| tei | ~93 MiB | ~91% | Low RSS (weights mmapped to page cache); CPU high while warming. |
| seaweedfs | ~77 MiB | ~33% | — |
| worker | ~80 MiB | ~2% | Idle — **balloons during ingestion** (parsing/ML). |
| docforge | ~64 MiB | ~9% | — |
| pgadmin | ~37 MiB | <1% | — |
| postgres | ~23 MiB | ~0% | — |
| frontend | ~14 MiB | ~11% | — |
| qdrant | ~10 MiB | <1% | Grows with indexed collections. |
| gotenberg | ~8 MiB | <1% | Spikes only during conversion. |
| mcp | ~6.5 MiB | <1% | — |
| redis | ~3 MiB | ~1% | — |

> ⚠️ Idle numbers under-represent **worker** and **gotenberg**, which are bursty:
> worker loads parsing/ML work per job, gotenberg spawns LibreOffice/Chromium per
> conversion. Their ceilings are sized for those bursts, not the idle baseline.

---

## 4. Monitoring & tuning

**Watch live usage** (the `MemPerc` column is relative to each container's limit,
so it directly shows headroom):

```bash
docker stats --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"
```

**Verify the applied ceilings on running containers:**

```bash
docker inspect <container> --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'
```

**Re-tune:** edit the `deploy.resources.limits` block of the service in
`docker-compose.yml` (or `docker-compose.dev.yml` for `frontend`), then
`docker compose up -d` — Compose recreates only the changed containers, no
rebuild needed.

**Watch for OOM kills** — if a service is `OOMKilled` (visible in
`docker inspect <c> --format '{{.State.OOMKilled}}'` or `docker events`), its
memory ceiling is too low for the workload; raise it rather than removing the cap.

---

## Related

- [Deployment guide](deployment.md) — production hardening, ports, secrets, GPU.
- [Configuration reference](configuration.md) — every environment variable per service.
- [PROD-HARDENING.md](PROD-HARDENING.md) — the exhaustive go-live runbook.
- Compose files — `docker-compose.rework.yml`, `docker-compose.rework.dev.yml`, `docker-compose.rework.gpu.yml`.
