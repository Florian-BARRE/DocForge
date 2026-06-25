---
name: model-host-contract
description: bge_server HTTP contract, env vars, rationale for replacing TEI, and how docforge consumes it
metadata:
  type: reference
---

`src/bge_server/` is a rule-compliant FastAPI micro-service (refactored 2026-06-24). Key files:
`entrypoint.py` (uvicorn target), `config_loader.py` (BgeServerConfig), `pyproject.toml`+`uv.lock`,
`Dockerfile` (2-stage uv build), `libs/bge_models/{service,device}.py`, `backend/{app,context,lifespan}.py`,
`backend/routers/{health,inference}/`, `backend/libs/utils/error_handling.py`.
WORKDIR inside Docker is `/app/bge_server`; uvicorn targets `entrypoint:app` (flat module name).
This is INFRA (a model host), deliberately OUTSIDE the docforge layer DAG.

**HTTP contract (TEI-compatible — frozen):**
- `POST /embed` — body `{inputs: str|list[str], normalize=true, truncate=true}` -> `[[float,...],...]`.
- `POST /embed_sparse` — body same -> `[[{"index":int,"value":float},...],...]`.
- `POST /rerank` — body `{query:str, texts:[str], truncate=true}` -> `[{"index":int,"score":float},...]`.
- `GET /health` — `{"status":"ok","embed_model":"...","rerank_model":"..."}`.

**Models** (both via `FlagEmbedding`, loaded once in lifespan, released on shutdown):
- Embed: `BGEM3FlagModel(BGE_M3_MODEL, devices=resolved_device, use_fp16=gated_fp16)`.
- Rerank: `FlagReranker(BGE_RERANKER_MODEL, devices=resolved_device, use_fp16=gated_fp16)`.
- ⚠️ **API GOTCHA** — resolved FlagEmbedding version is **1.4.0** (uv.lock). In 1.3+ BOTH the
  embedder AND the reranker take `devices=` (PLURAL — accepts a str like `"cpu"`/`"cuda"`, an int,
  or a list). The singular `device=` is the PRE-1.3 API; on 1.4.0 it is wrong (swallowed into
  `**kwargs` and silently IGNORED → model runs on the auto-detected device, not the resolved one).
  Verified against the official FlagEmbedding docs. Never write `device=` here.

**Device management** (`libs/bge_models/device.py` — `DeviceResolver` static helper):
- `BGE_DEVICE=auto` -> `cuda` if available else `cpu` (safe default, no loud failure).
- `BGE_DEVICE=cuda` -> requires CUDA; RuntimeError if not available (no silent fallback).
- `BGE_DEVICE=cpu` -> always CPU.
- `BGE_FP16` is GATED: forced off on CPU even if true (warning logged). fp16 on CPU is a footgun.
- Validation in `BgeServerConfig.validate()` rejects unknown BGE_DEVICE values — but `EnvConfigLoader`
  does NOT auto-call `validate()`. It is invoked explicitly in `backend/lifespan.py` (after the config
  log, BEFORE `bge_models.load()` so a bad policy aborts before downloading ~4.4 GiB). Same convention
  as the docforge app (`app/backend/lifespan.py` calls `RUNTIME_CONFIG.validate()`).
- `BgeModelsService` exposes public `resolved_device` + `use_fp16` properties (gated value) — the
  lifespan boot summary reads those, never the `_use_fp16` protected attr.
- GPU compose reservation: commented-out `reservations.devices` block in `docker-compose.yml`.

**Env vars (all have safe defaults — service starts without .env):**
- `BGE_DEVICE` (default `auto`), `BGE_M3_MODEL` (default `BAAI/bge-m3`),
  `BGE_RERANKER_MODEL` (default `BAAI/bge-reranker-v2-m3`), `BGE_FP16` (default `false`),
  `BGE_M3_MAX_LENGTH` (default `8192`), plus 5 `LOGGING_*` vars.
- `BGE_MAX_CONCURRENCY` (default `2`): semaphore limit on simultaneous inference calls across
  all three endpoints. Requests beyond the limit queue (asyncio wait), never reject.
- `BGE_TORCH_NUM_THREADS` (default `0` = auto = `ceil(cpu_count / BGE_MAX_CONCURRENCY)`):
  `torch.set_num_threads()` cap applied once in `BgeModelsService.load()`.
- Template: `services/bge_server/.env.example`.

**Why it exists:** off-the-shelf HuggingFace TEI crash-loops on BGE-M3's ONNX backend (exit-0,
RestartCount climbing into the hundreds) AND cannot produce BGE-M3 sparse. This ONE service replaces
both the old `tei` embed container and the `reranker` container.

**Dual-variant build (ARG TORCH_VARIANT, validated 2026-06-24):**
- `cpu` (default, `docforge-bge-server:latest`): **1.94 GB**, torch 2.12.1+cpu, 0 nvidia-* libs.
  `docker compose build bge_server` — uses `TORCH_VARIANT: cpu` arg set in docker-compose.yml.
- `gpu` (opt-in, `docforge-bge-server:gpu`): **9.47 GB**, torch 2.6.0+cu124, nvidia-cu12-* runtime.
  `docker build --build-arg TORCH_VARIANT=gpu -f src/bge_server/Dockerfile -t docforge-bge-server:gpu src`
- Both torch entries live in `uv.lock` under marker `extra == cpu` / `extra == gpu`.
  The `conflicts` declaration in pyproject.toml makes them mutually exclusive.
- torch was declared as a DIRECT dep in `[project.optional-dependencies]` to make uv sources work
  (uv sources are ignored for transitive deps — that was the original bug).
- transformers pin `>=4.45,<5` must stay: FlagReranker 1.4.0 breaks on transformers 5.x (removes
  `prepare_for_model` slow-tokenizer API). /rerank fails silently past health checks if unpinned.

**Deployment (must stay aligned — see [[provider-config-per-collection]] in user memory):**
- compose service `bge_server`, image `docforge-bge-server:latest`, hostname `http://bge_server:80`.
- build `src/bge_server/Dockerfile` (context `src/`); volume `bge_models` (HF cache, `HF_HOME=/models`).
- compose wires `env_file: services/bge_server/.env` and `build.args.TORCH_VARIANT: cpu`.
- compose has a `/health` healthcheck (stdlib urllib probe, `start_period: 300s` to cover the slow
  weight download) so dependents can gate on `condition: service_healthy`.
- GPU runtime: uncomment `reservations.devices` in compose + `BGE_DEVICE=cuda` in .env + gpu image.

**Dockerfile gotchas:**
- ⚠️ NEVER add a `uv pip install ...` step BEFORE `uv sync`: `/opt/venv` does not exist until `uv sync`
  creates it → "No virtual environment found for path". A prior version broke on this.

**GPU VALIDATED (2026-06-24, RTX 4050 Laptop 6 GB, driver 581.29, Docker nvidia runtime):** built the
image, ran `docker run --gpus all -e BGE_DEVICE=cuda -e BGE_FP16=true`. `cuda_available=True` inside the
container; all 3 endpoints work on GPU — /embed (1024-dim), /embed_sparse (TEI shape), /rerank (correct
semantic scores: GPU-answer 0.967 vs off-topic 2e-5). fp16 keeps both models well within 6 GB VRAM.

**How docforge consumes it (NO new provider code):** the existing `tei` embed provider + `bge`/
`bge_reranker` rerank providers drive it. A collection's `base_url` defaults to the structural
`http://bge_server:80` (per-collection config, never `.env`). If the compose service name ever changes,
the structural default `http://bge_server:80` must change in lockstep across the embed/rerank/semantic
config defaults in `common_libs` (see code-reviewer's product memory).

**Concurrency control (added 2026-06-25):** `asyncio.Semaphore(BGE_MAX_CONCURRENCY)` created in
`lifespan.py` step 3, stored on `CONTEXT.inference_semaphore`. The three inference router handlers
each do `async with CONTEXT.inference_semaphore:` around the model call. Empty-list fast-paths
return before acquiring. Torch threads capped via `torch.set_num_threads()` in `BgeModelsService.load()`
step 3 (auto = `ceil(cpu_count / max_concurrency)`, override via `BGE_TORCH_NUM_THREADS`).

**Readiness gate (added 2026-06-25):** `GET /health` returns HTTP 503 + `{status:"loading", ready:False}`
while models load (checks `bge_models._embed_model is None`). Returns HTTP 200 + `{ready:True}` after.
`HealthResponse` now has a `ready: bool` field. The TEI callers that checked for 200/ok still work;
the compose healthcheck already uses `start_period=300s` and will retry on 503.

**Dynamic batching (2026-06-25, GPU-verified):** inference is NOT called directly anymore — it goes
through `libs/batching/` (`BatchingEngine` + 3 `BatchQueueWorker`, in-process `asyncio.Queue`, NEVER
Redis). Handlers `await CONTEXT.batching_engine.submit_{embed_dense,embed_sparse,rerank}`; each worker
drains its queue (Σcost >= `BGE_MAX_BATCH_SIZE` or `BGE_MAX_WAIT_MS` window), runs ONE batched model call
via `asyncio.to_thread` under ONE shared `asyncio.Lock` (dense+sparse share `embed_model` -> mandatory),
scatters by offsets. Cost units = texts (embed) / pairs (rerank); rerank flattens pairs across requests
then **re-indexes 0..n-1 per request**. Bounded queue full -> `QueueFullError` -> HTTP 503 + Retry-After.
`stop()` drains pending futures (no client hangs). Env: `BGE_MAX_BATCH_SIZE=32`/`BGE_MAX_WAIT_MS=10`/
`BGE_MAX_QUEUE_SIZE=256` (batch=1+wait=0 disables). `BGE_MAX_CONCURRENCY` REMOVED (superseded).
`service.compute_rerank_scores_flat(pairs)` is the engine's rerank entry. Verified RTX 4050: 50 concurrent
/embed in ~1.1 s (batches of 23/11/8...), /health stays 200 (~100 ms) under load. RPI docs:
`docs/rpi/bge-server-dynamic-batching/`. Do NOT reintroduce direct model calls in the router or a
per-worker lock.

**Logging coverage (full):** `LoggerClass` on `BgeModelsService` (`self.logger`); module-level
`loggerplusplus.bind` for lifespan (`BGEServer`), routers (`InferenceRouter`/`HealthRouter`),
error_handling (`ErrorHandler`), DeviceResolver, entrypoint (`BGEEntrypoint`).
**Level discipline (keep it):** INFO = lifecycle ONLY (model load steps, ready banner, device
resolution, shutdown). DEBUG = per-request + per-call tracing (router `POST /embed: N inputs`,
service `encode_dense: N texts -> N vecs in 0.3s (device=cpu)`, `GET /health`) — these are
high-frequency and would FLOOD logs at INFO. WARNING = fp16-on-CPU override. Inference logs counts +
timing + device ONLY, never payload text (huge/sensitive). `helpers.py` has NO logger (tracing lives
in router.py where batch size is known).

**Invariant:** all runtime-emitted strings stay ASCII (Windows cp1252 console — use `->`, never the
arrow char). Non-ASCII is fine in comments/docstrings.
