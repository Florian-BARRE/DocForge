# DocForge — Resource Footprint & Hardware Sizing

How much CPU/RAM/disk/GPU each service costs, the per-service ceilings enforced in
`compose/base.yml`, and a decision table that maps *your* model/feature choices onto a
concrete machine. Every number below was verified against the current compose files
(`compose/base.yml`, `compose/overlays/gpu.yml`) and, where marked **(observed)**, against a
live stack running on this repo's reference dev VM. Anything not directly measurable is marked
**(estimate)** with its basis — do not treat those as guarantees.

> **This file replaces an older version that listed `tei` + `reranker` as separate services and a
> `pgadmin` container.** Neither exists anymore: `bge_server` hosts BOTH BGE-M3 embedding *and*
> the BGE-reranker-v2-m3 cross-encoder in one process, and there is no `pgadmin` in the compose
> at all. The stack also gained a new sidecar, `paddle_server` (PP-StructureV3), since the last
> revision of this doc.

---

## TL;DR — minimal config to run DocForge

**No GPU needed.** The stock pipeline (parser `docling` + bundled `rapidocr` OCR + `bge_server`
CPU embedding) is 100% CPU, and every provider-hosted stage (figure-VLM enrich, LLM
contextualize/metagen) **ships OFF by default** — a fresh collection ingests with **zero external
API calls and zero external keys**.

| Resource | Minimum | Comfortable |
|---|---|---|
| RAM | 8 GB (tight — see reasoning below) | **12–16 GB** |
| CPU | 4 cores, no special instruction set required | 8 cores |
| Disk | 15 GB | **20 GB** |
| GPU | none | none |

**Reasoning, not a guess:** the two heaviest services alone (`worker` 5 GiB ceiling + `bge_server`
5 GiB ceiling) already sum to 10 GiB if both hit their cap simultaneously, and the rest of the
minimal set (app + postgres + redis + qdrant + seaweedfs + gotenberg + mcp) idles at roughly
1.5–2 GiB combined (see §3, observed). Ceilings are **not** reservations — see §2 — so 8 GB is
survivable for light/no-concurrent-ingestion use but leaves no headroom; 12–16 GB is the
realistic-peak-plus-headroom number for actual document ingestion traffic.

**Reconciling the old "~10 GB disk / ~8 GB RAM" claim in `getting-started.md`:** that number
predates `paddle_server` and the current `bge_server`/`worker` ceilings (5g each, up from
smaller values). It is now optimistic on both counts — disk is closer to **18–20 GB** once the
BGE-M3 first-boot download is counted (see §4), and 8 GB RAM is a bare floor, not a comfortable
number. `getting-started.md` should be revisited to match this doc (flagged, not changed here per
scope — this pass only refreshes `deployment-resources.md`).

---

## 1. What actually runs — current topology

Prod topology (`compose/prod-cpu.yml`, pulls `ghcr.io/florian-barre/docforge-*` images, no build):

| Service | Role | Profile |
|---|---|---|
| `docforge_app` | FastAPI + compiled React UI (light image, no docling) | `full` |
| `docforge_worker` | arq worker — runs the ingest pipeline (docling, chunking, etc.) | `full` |
| `docforge_postgres` | Postgres 16 — catalogue, jobs, IR metadata | (base) |
| `docforge_redis` | arq queue transport only (no monitoring truth) | (base) |
| `docforge_qdrant` | Vector store — dense + sparse per collection | (base) |
| `docforge_seaweedfs` | S3-compatible blob store | (base) |
| `docforge_gotenberg` | Office → PDF conversion (LibreOffice + Chromium) | (base) |
| `docforge_bge_server` | **BGE-M3 embed (dense+sparse) + BGE-reranker-v2-m3 — replaces the old separate `tei`+`reranker`** | `full`, `bge` |
| `docforge_mcp` | Standalone MCP server — pure HTTP client of the API, no DB/S3 | `full` |
| `docforge_paddle_server` | PP-StructureV3 layout-parsing sidecar — **new since the last revision of this doc** | `full` |

`compose/overlays/dev.yml` (via `compose/dev-cpu.yml`/`compose/dev-gpu.yml`) adds a dev-only `docforge_frontend` (Vite dev server, hot reload) and
switches app/worker/mcp/bge_server/paddle_server to local builds. **No `pgadmin` container exists
anywhere in this stack.** `compose/overlays/gpu.yml` overlays GPU images + `gpus: all` onto
`worker`, `bge_server`, and `paddle_server` (the only three torch/paddle-bearing services).

Bring-up:
```bash
# Prod CPU (default)
docker compose --profile full up -d
# Prod GPU
docker compose -f compose/prod-gpu.yml --profile full up -d
```
`--profile full` is required for app/worker/mcp/paddle_server/frontend — omit it and only the
data-plane stores start.

---

## 2. Per-service RAM ceilings (verified in `compose/base.yml`)

> **No `cpus:` limit is set on any service, anywhere in the compose files.** The previous version
> of this doc listed a CPU ceiling per service — that was never actually enforced; there is no
> `deploy.resources.limits.cpus` block on any service today. CPU usage is **unbounded** — the
> worker's own in-file comment explicitly says native BLAS/OpenMP threads are "LEFT UNPINNED... so
> docling/torch/onnx use all available cores." Plan CPU by **core count available to Docker**, not
> by a per-service cap.

| Service | RAM limit | RAM reservation | Notes |
|---|---|---|---|
| `docforge_app` | 2 GiB | — | I/O-bound; light image |
| `docforge_worker` | 5 GiB | 1 GiB | Idle ~0.9 GiB per in-file comment; a large PDF + OCR peaks 2–4 GiB; **observed (live, 3-wk-uptime dev box) 4.46 GiB / 89% of ceiling** — a busy worker can approach its cap |
| `docforge_postgres` | 4 GiB | 1 GiB | Tuned off stock 128 MB profile (`shared_buffers=1GB`, `effective_cache_size=3GB`) |
| `docforge_redis` | 512 MiB | 128 MiB | `maxmemory 400mb`, `noeviction`, RDB snapshots disabled — transport only, no monitoring truth |
| `docforge_qdrant` | 4 GiB | 1 GiB | Grows with indexed collection size |
| `docforge_seaweedfs` | 1 GiB | — | Object gateway, light steady-state |
| `docforge_gotenberg` | 2 GiB | — | LibreOffice/Chromium spike per conversion |
| `docforge_bge_server` (cpu) | 5 GiB | 3.5 GiB | Both models (BGE-M3 + reranker) resident ~3.5 GiB per in-file comment; **observed (live) 2.82 GiB / 56%** |
| `docforge_mcp` | 512 MiB | — | Pure HTTP client, no DB/S3; **observed (live) 21.8 MiB** |
| `docforge_paddle_server` (cpu) | **16 GiB** | 1 GiB | PP-StructureV3 loads ~7 CPU models (layout+OCRv5+table+formula/seal heads); ceiling sized for a predict() spike, not idle. **Observed (live, after prior pp_structure use) 2.48 GiB / 15.5%** — a never-used cold instance is lighter, but budget for multi-GiB spikes once a collection actually selects `pp_structure` |
| `docforge_frontend` (dev only) | **not set** | — | No `deploy.resources` block exists for it in `compose/overlays/dev.yml` — unconstrained. Vite dev server; typically light (~100–300 MB) |

**Sum of ceilings, full CPU profile (all 10 prod services): ≈ 24 GiB.** This is intentionally
larger than any reasonable single box — ceilings are hard caps, not reservations, and they don't
all peak together. Use §3's observed numbers, not this sum, for capacity planning.

---

## 3. Observed live consumption (this repo's reference dev VM, 3-week uptime, `--profile full` up, not actively ingesting)

```
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"
```

| Service | Mem (observed) | % of ceiling | Note |
|---|---|---|---|
| `docforge-worker` | 4.46 GiB | 89% | High for "idle" — docling's process-wide model cache accumulates across a long uptime; the in-file comment's 0.9 GiB idle figure is closer to a cold-started worker |
| `docforge-bge-server` | 2.82 GiB | 56% | Both models loaded, keep-warm active |
| `docforge-paddle-server` | 2.48 GiB | 15.5% | Reflects prior `pp_structure` use on this box, not a cold-never-used instance |
| `docforge-gotenberg` | 1.06 GiB | 53% | LibreOffice stays warm once spawned |
| `docforge-app` | 294.8 MiB | 14.4% | — |
| `docforge-seaweedfs` | 406.6 MiB | 39.7% | — |
| `docforge-qdrant` | 199.2 MiB | 4.9% | Grows with indexed data |
| `docforge-postgres` | 195.1 MiB | 4.8% | — |
| `docforge-frontend` (dev) | 198.3 MiB | — | No ceiling configured |
| `docforge-mcp` | 21.8 MiB | 4.3% | — |
| `docforge-redis` | 9.1 MiB | 1.8% | — |

**Total observed, full profile (excl. frontend): ≈ 12.1 GiB.** Excluding `paddle_server`
(minimal/stock profile): **≈ 9.6 GiB.** This is a *used* box (residual caches from real ingestion
jobs), which makes it a better realistic-peak proxy than a synthetic cold-idle snapshot — treat it
as the number to size against, not the ceiling sum.

Host context on this VM (shared with other projects — do not read this row as "DocForge alone
needs 31 GiB"): `free -h` shows 31 GiB total, ~19 GiB used across ALL projects/containers on the
box, ~12 GiB available. `nproc` = 8 cores, no CPU pinning applied to any DocForge container.

---

## 4. Disk — images + first-boot model downloads

**Image sizes** (measured with `docker images` on this VM; CPU-tier images, current tags):

| Image | Size |
|---|---|
| `docforge-worker` (cpu) | 2.92 GB |
| `docforge-paddle-server` (cpu) | 2.30 GB |
| `gotenberg/gotenberg:8` | 2.44 GB |
| `docforge-bge-server` (cpu) | 1.94 GB |
| `postgres:16-bookworm` | 622 MB |
| `docforge-app` | 612 MB |
| `chrislusf/seaweedfs:4.38` | 360 MB |
| `qdrant/qdrant:v1.18.2` | 270 MB |
| `docforge-mcp` | 265 MB |
| `redis:7-bookworm` | 170 MB |

- **Minimal profile images (no `paddle_server`): ≈ 9.6 GB.**
- **Full CPU profile images (incl. `paddle_server`): ≈ 11.9 GB.**

**First-boot model downloads (NOT baked into images — pulled from HuggingFace on first request):**

| Model cache | Compose in-file estimate | Observed volume size (this VM) |
|---|---|---|
| `bge_server` (BGE-M3 + reranker) | "~4.4 GiB" (healthcheck comment) | **6.4–6.9 GB** (`docforge_docforge_bge_models` volume, `du -sh`) |
| `paddle_server` (PP-StructureV3, lean default: layout+OCRv5+table) | "≈270 MB lean default" (healthcheck comment) | **1.0–1.1 GB** (`docforge_docforge_ppstructure_models` volume) |
| worker (docling + rapidocr models via HF cache) | not documented in compose | **~1.0 GB (estimate)** — based on this VM's host HF cache dir (`~/.cache/huggingface`, 1012 MB); this directory may include models from other non-DocForge tooling on a shared dev machine, so treat as an upper-bound estimate, not a clean measurement |

Both in-file estimates undercount the real observed volume size — HuggingFace's local cache keeps
blob + snapshot layers that don't fully dedupe, so plan disk against the **observed** column, not
the compose comment.

**Total disk, minimal/stock profile:** images (9.6 GB) + bge model download (6.5–6.9 GB) + data
growth headroom (~2 GB for postgres/qdrant/seaweedfs as they fill) ≈ **18–20 GB**. This is the
number that corrects `getting-started.md`'s stale "~10 GB" claim.

**Total disk, full CPU profile (adds `paddle_server`):** + 2.3 GB image + ~1.1 GB model cache ≈
**22–24 GB**, round up to **30 GB** for comfortable headroom (docker build cache, logs, growing
collections).

---

## 5. GPU images and sizing (from `compose/overlays/gpu.yml` + per-service Dockerfile/`.env.example` comments — not locally measured, no GPU on this dev VM)

`compose/overlays/gpu.yml` swaps `worker`, `bge_server`, and `paddle_server` to `-gpu` image tags and
grants `gpus: all` to all three (the only torch/paddle-bearing services — `app`, `postgres`,
`redis`, `qdrant`, `seaweedfs`, `gotenberg`, `mcp` are never GPU-aware).

| Service (gpu tag) | Image size (documented estimate) | Torch/Paddle payload |
|---|---|---|
| `docforge-worker-gpu` | **~8.5 GB (estimate)** — CI commit `8834062` needed to reclaim disk on GitHub Actions runners specifically because "the CUDA images (~8.5 GB)" overflowed the ~14 GB free on a stock runner | torch 2.6.0+cu124 (~2 GB wheel) + CUDA 12.4 runtime libs, vs ~200 MB CPU wheel |
| `docforge-bge-server-gpu` | **~9.5 GB (estimate, from `services/bge_server/.env.example`)** | same torch cu124 wheel + nvidia-cu12-* libs |
| `docforge-paddle-server-gpu` | **~4–5.5 GB (estimate, from Dockerfile comment)** | paddlepaddle-gpu 3.3.1, CUDA 12.6, vs ~100 MB CPU wheel |

**vRAM (estimate — no GPU hardware was available to measure on this pass):** BGE-M3 + reranker
are both ~568 M-parameter models; fp16 weights alone are roughly 1.1 GB each, so `bge_server-gpu`
running both concurrently needs on the order of **3–5 GB vRAM** with activation/batch headroom.
Granite-Docling-258M is a small VLM; **2–4 GB vRAM (estimate)** for weights + per-page inference.
PP-StructureV3-gpu runs several detection/recognition sub-models; **2–4 GB vRAM (estimate)**. If
`worker`, `bge_server`, and `paddle_server` share a **single physical GPU** (the common case for a
single-box deploy — `gpus: all` grants the whole device to each container, they don't partition
it), size for the sum with headroom: **≥16 GB vRAM** for a comfortable single-GPU full-profile
deployment; a leaner GPU box running only `bge_server-gpu` (embed+rerank, no granite/pp_structure)
can work with **8 GB vRAM**.

---

## 6. Choice → machine decision table

Pick your rows, sum the "extra" columns onto the minimal baseline (§ TL;DR) to land on a machine.

| Choice | Extra RAM | GPU needed? | Extra disk | External API? | Notes |
|---|---|---|---|---|---|
| **Parser: `docling`** (default) | included in worker's 5g ceiling | No | included in worker image | No | Bundles RapidOCR. This is the minimal/stock path. `do_ocr=false` always — structure only, scans become full-page figures handled downstream |
| **Parser: `pp_structure`** | +16g ceiling (`paddle_server`, 1g reservation; real spikes several GB) | Optional (CPU works, GPU speeds it up) | +2.3 GB image (cpu) / +4–5.5 GB (gpu, estimate) + ~1.1 GB model cache | No | **Requires a CPU with AVX support** (`enable_mkldnn=False` is set to dodge a PaddlePaddle 3.x PIR-executor bug, but AVX itself is a hard floor — a non-AVX CPU SIGILLs). Observed ~18–20s/page on CPU (demo-collection memory) — plan node `timeout_seconds` accordingly. Folds bullet lists into paragraphs (loses list granularity vs docling) but detects running headers/footers |
| **Parser: `granite_docling`** | none extra (runs IN-worker, no sidecar) | **Yes, GPU-in-practice** | +~1 GB (estimate) added to worker's HF cache for the 258M model | No | Confirmed hangs at 0% CPU on a CPU worker (demo-collection memory) — treat as GPU-only despite being "just" a 258M model; do not enable on a CPU deploy |
| **OCR: `rapidocr`** (default) | included in worker image | No | included in worker image | No | Local ONNX, bundled — part of the minimal path |
| **OCR: `mistral`** | ~0 | No | ~0 | **Yes** (key + network) | Escalation queue behind rapidocr via `ScoreBelow`; no local compute cost, but adds an external dependency + per-call cost |
| **VLM figure-enrich: hosted (OpenAI-compat)** | ~0 | No | ~0 | **Yes** (key + network) | **OFF by default** in the stock template — the ENRICH stage's VLM classify/describe chain ships disabled so a fresh collection needs zero external config |
| **VLM figure-enrich: self-hosted** | entirely external, not sized here | Yes (on the user's own box) | entirely external | No (self-hosted) | DocForge does not ship a VLM host — only an OpenAI-compat *client* node; bring your own GPU server outside this compose |
| **LLM contextualize/metagen/query-rewrite: hosted (OpenAI-compat / Mistral)** | ~0 | No | ~0 | **Yes** (key + network) | **OFF by default**, same reasoning as VLM |
| **LLM: self-hosted** | entirely external, not sized here | Yes (on the user's own box) | entirely external | No (self-hosted) | Same caveat as VLM self-host |
| **Embed: `bge_server` (BGE-M3, local)** (default) | +5g ceiling / 3.5g reservation (cpu) or GPU image | Optional (cpu default, `-gpu` overlay available) | +1.94 GB image (cpu) / ~9.5 GB (gpu, estimate) + 6.4–6.9 GB model download | No | Dense **+ sparse** — the product default. Also hosts the reranker in the same process |
| **Embed: OpenAI-compat endpoint** | ~0 local | No | ~0 | **Yes** (key + network) | Dense-only — no sparse vector, so lexical/hybrid search on that field loses its sparse axis |
| **Rerank: BGE-reranker-v2-m3 (in `bge_server`)** | included in bge_server's ceiling if enabled | No (works on CPU) but **impractical on CPU for production** | none extra (same process) | No | **OFF by default.** Measured CPU ceiling: ~1.6s/passage, top_n=5→9s up to top_n=50→79s (8-core container) — the built-in 12s degrade-after kicks in past ~top_n=8-10, silently falling back to fusion-order results. Production path is a hosted/GPU reranker via the per-collection `base_url` override, not the in-stack CPU one |
| **torch/paddle variant: cpu** (default) | baseline (§2/§4) | No | baseline | No | ~200 MB torch wheel / ~100 MB paddle wheel |
| **torch/paddle variant: gpu** | same RAM ceilings, PLUS GPU vRAM (§5) | **Yes** — NVIDIA Container Toolkit required | +5.5–7.5 GB per swapped image (§5) | No | Only `worker`, `bge_server`, `paddle_server` have `-gpu` tags — use `compose/prod-gpu.yml` / `compose/dev-gpu.yml` |

---

## 7. Three worked profiles

### (a) Minimal / smallest — CPU, stock defaults, zero external API

Services: `app`, `worker` (cpu), `postgres`, `redis`, `qdrant`, `seaweedfs`, `gotenberg`,
`bge_server` (cpu). Skip `paddle_server` and `mcp` if not needed (start them by name instead of
`--profile full` to exclude `paddle_server`'s 16g ceiling and 2.3 GB image). Parser `docling` +
bundled `rapidocr`; VLM/LLM stages left OFF (the shipped default).

| | |
|---|---|
| RAM | **12 GB** (8 GB survives light single-user testing, no headroom) |
| CPU | 4 cores, no AVX requirement |
| Disk | **20 GB** |
| GPU | None |

### (b) Balanced self-hosted CPU — full profile, `pp_structure` available, rerank considered but left off

Adds `paddle_server` (idle unless a collection selects `pp_structure`) and `mcp`. Embed + optional
rerank both via `bge_server` CPU — rerank explicitly **left disabled** per the measured CPU ceiling
in §6 (production-quality rerank needs GPU/hosted, not this box).

| | |
|---|---|
| RAM | **24 GB** (covers worker+bge_server ceilings concurrently plus paddle_server headroom for occasional pp_structure jobs) |
| CPU | 8 cores, **AVX required** (for `pp_structure`) |
| Disk | **30 GB** |
| GPU | None |

### (c) Full / GPU — granite_docling parser + GPU embed/rerank + pp_structure

`compose/prod-gpu.yml`, `--profile full`. `worker`, `bge_server`,
`paddle_server` all GPU. VLM/LLM stages may stay on hosted APIs (no self-host required for those
— DocForge doesn't ship a VLM/LLM host) or point at an external self-hosted endpoint outside this
compose.

| | |
|---|---|
| RAM (system) | **32 GB** |
| CPU | 8+ cores |
| Disk | **45–50 GB** (GPU images run 5.5–7.5 GB larger each than their CPU counterparts, §5) |
| GPU | **Required** — NVIDIA GPU + Container Toolkit, **≥16 GB vRAM** for comfortable concurrent worker+bge_server+paddle_server load on one device (estimate, §5); 8 GB vRAM is enough for a GPU box running only `bge_server-gpu` (embed+rerank) with the other two still on CPU |

---

## 8. Monitoring & tuning

**Watch live usage** (the `MemPerc` column is relative to each container's configured limit):

```bash
docker stats --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}"
```

**Verify the applied RAM ceiling on a running container** (there is no CPU ceiling to verify — see
§2, none is configured):

```bash
docker inspect <container> --format '{{.HostConfig.Memory}}'
```

**Re-tune:** edit the `deploy.resources.limits`/`reservations` block of the service in
`compose/base.yml` (memory only — there is no `cpus:` knob today), then `docker compose up -d` —
Compose recreates only the changed container, no rebuild needed.

**Watch for OOM kills** — if a service is `OOMKilled`:

```bash
docker inspect <container> --format '{{.State.OOMKilled}}'
```

Raise its `limits.memory` rather than removing the cap. `docforge_worker` and `docforge_paddle_server`
are the two most likely candidates under real ingestion/`pp_structure` load per §3.

**Check disk before a mysteriously stuck/timed-out ingestion job** — a full disk on this class of
VM has previously caused silent swap-thrash timeouts, not a clean error:

```bash
df -h /
docker system df -v
```

**Volume sizes** (model caches, blob store, vector index):

```bash
docker system df -v | grep docforge
```

---

## Related

- [Deployment guide](deployment.md) — production hardening, ports, secrets, GPU bring-up.
- [Configuration reference](configuration.md) — every environment variable per service.
- [PROD-HARDENING.md](PROD-HARDENING.md) — the exhaustive go-live runbook.
- Compose files — `compose/base.yml`, `compose/overlays/{dev,gpu}.yml`, `compose/{prod,dev}-{cpu,gpu}.yml` (see `compose/README.md`).
