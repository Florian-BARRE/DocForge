# BGE model-suite micro-service

A small, fully local embedding + reranking server that hosts:

- **BAAI/bge-m3** via `BGEM3FlagModel` -- producing **dense** (1024-dim L2-normalized),
  **native multilingual sparse** (lexical weights), and **native ColBERT** (per-token multi-vector)
  representations from the same loaded model instance.
- **BAAI/bge-reranker-v2-m3** via `FlagReranker` -- cross-encoder reranking with sigmoid-normalized
  scores.

Both models run via **FlagEmbedding (torch)**, loaded once at startup on CPU by default. The service
speaks the **same HTTP contract as HuggingFace TEI** (`/embed`, `/embed_sparse`, `/rerank`, `/health`)
so DocForge drives it with the **existing `tei` embed provider and `bge_reranker` rerank provider --
no new provider code needed**. `/embed_colbert` is an additional, internal-only DocForge convention
(no TEI equivalent).

## Why this and not TEI / Infinity

- **TEI** `/embed_sparse` is SPLADE-only -- it returns HTTP 424 for BGE-M3 (cls pooling) -- dense only.
- **SPLADE** models are English-centric -- poor multilingual sparse.
- **BGE-M3 via FlagEmbedding** = one multilingual model, dense + sparse in one pass, API we control.

## Endpoints (TEI-compatible contract -- frozen)

| Method | Path | Request body | Response |
|---|---|---|---|
| GET  | `/health` | -- | `{"status":"ok","ready":true,"detail":null,"device":"cpu","embed_model":"...","rerank_model":"..."}` (HTTP 503, `"status":"loading"`, while the models load) |
| POST | `/embed` | `{"inputs": "..." or ["..."], "normalize": true, "truncate": true}` | `[[float, ...], ...]` (dense 1024-dim) |
| POST | `/embed_sparse` | `{"inputs": "..." or ["..."], "truncate": true}` | `[[{"index": int, "value": float}, ...], ...]` |
| POST | `/rerank` | `{"query": "...", "texts": ["..."], "truncate": true}` | `[{"index": int, "score": float}, ...]` |

Rerank scores are sigmoid-normalized to `[0, 1]`. Results are returned in **input order** -- the
DocForge `bge_reranker` provider re-sorts by index.

## Endpoint (internal DocForge convention -- NOT part of the TEI contract)

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/embed_colbert` | `{"inputs": "..." or ["..."], "truncate": true}` | `[[[float, ...], ...], ...]` (per text, per-token 1024-dim vectors, variable length) |

BGE-M3's native ColBERT multi-vector head -- one L2-normalized 1024-dim vector per real token
(length = token count - 1, CLS row dropped). TEI has no colbert primitive, so this endpoint has no
upstream contract to mirror; it exists solely for DocForge-internal late-interaction use cases.

## Source layout

The service is built on the shared `src/model_server_core` library: the core owns the app skeleton
(config base, lifespan with fail-fast config validation, gzip, `GET /health`, typed error handler,
request guards, device probe, CPU budget, logging bootstrap); this folder only holds what is BGE's own.

```
src/bge_server/
  entrypoint.py          # uvicorn target: ServerEntrypoint(BgeServer(BgeServerConfig)), zero logic
  config_loader.py       # BgeServerConfig(ServerConfig) -- the BGE_* env vars
  pyproject.toml         # uv-managed dependencies (FlagEmbedding, fastapi, ..., model_server_core path dep)
  uv.lock                # locked dependency graph
  Dockerfile             # 2-stage uv build; copies ../model_server_core; CPU torch from the PyTorch index
  libs/
    bge_models/
      service.py         # BgeModelsService(ModelService) -- loads/unloads both models, encode/rerank
      device.py          # DeviceResolver -- BGE_DEVICE policy -> concrete device + fp16 gate
      torch_cuda_detector.py  # TorchCudaDetector -- the torch GPU check injected into the core DeviceProbe
    batching/
      models.py          # BatchItem/EmbedItem/RerankItem dataclasses + QueueFullError
      worker.py          # BatchQueueWorker(LoggerClass) -- one generic micro-batcher per op
      engine.py          # BatchingEngine(LoggerClass) -- owns 5 workers + the embed/rerank locks
  backend/
    bge_server.py        # BgeServer(ModelServer) -- title, model service, routes, gzip level, /health body
    bge_health_response.py   # BgeHealthResponse -- core HealthResponse + the two model ids
    runtime/             # BgeRuntime: batching engine start/stop, warmup, keep-warm, ready summary
    routers/inference/   # InferenceRoutes: POST /embed, /embed_sparse, /embed_all, /embed_colbert, /rerank
  tests/
    unit/                # batching engine, admission, routes, health, runtime (mocked models, no torch)
    characterization/    # OpenAPI golden + wire goldens of the inference routes
services/bge_server/
  .env.example           # all env var defaults
```

## Errors

An unexpected exception answers **HTTP 500** with a generic typed body and a correlation id; the
exception itself (type, message, traceback) is only in the server log, under the same id:

```json
{"detail": {"error": "Internal server error. The details were logged.", "correlation_id": "<uuid hex>"}}
```

The id is also sent as the `X-Correlation-ID` response header. Deliberate `503` answers
(queue full, reranker not loaded) and `422` validation errors are unchanged.

## Build — two torch variants

The Dockerfile supports two mutually exclusive torch variants selected at build time via
`--build-arg TORCH_VARIANT`. The default is `cpu`.

| Variant | Torch version | nvidia-* libs | Approximate image size | CUDA available |
|---|---|---|---|---|
| `cpu` (default) | 2.13.0+cpu | none | ~2 GB | no |
| `gpu` | 2.13.0+cu129 | yes (cu12-*) | ~9.5 GB | yes (with --gpus) |

```bash
# CPU variant (default) — used by docker compose build, no flags needed:
docker compose build bge_server

# Or equivalently with explicit arg:
docker build -f src/bge_server/Dockerfile -t docforge-bge-server:latest src

# GPU variant (opt-in) — CUDA 12.8, compatible with RTX 40xx (Ada, compute 8.9):
docker build --build-arg TORCH_VARIANT=gpu \
  -f src/bge_server/Dockerfile -t docforge-bge-server:gpu src

# Also via compose for the GPU variant:
docker compose build --build-arg TORCH_VARIANT=gpu bge_server
```

To use the GPU image at runtime, three things are required:
1. Build with `TORCH_VARIANT=gpu` (above).
2. Set `BGE_DEVICE=cuda` (or `auto`) in `services/bge_server/.env`.
3. Uncomment the `reservations.devices` GPU block in `docker-compose.yml` and ensure the
   NVIDIA Container Toolkit is installed on the Docker host.

## docker compose service

Already wired in `docker-compose.yml` as the `bge_server` service (internal port 80, volume `bge_models`).
Default build produces the CPU variant (~2 GB).

## Wire a DocForge collection

Point the collection's embed and rerank providers at this service via per-collection config
(never in `.env`):

```json
{
  "pipeline": {
    "embed": {
      "chain": [
        { "id": "tei", "base_url": "http://bge_server:80", "embed_sparse": true }
      ]
    },
    "search": {
      "rerank": {
        "enabled": true,
        "chain": [
          { "id": "bge_reranker", "base_url": "http://bge_server:80" }
        ]
      }
    }
  }
}
```

## Config / env

All vars have safe defaults -- the service starts with no `.env` file. Copy
`services/bge_server/.env.example` to `services/bge_server/.env` to override.

| Env var | Default | Purpose |
|---|---|---|
| `BGE_M3_MODEL` | `BAAI/bge-m3` | HuggingFace model ID for the embed model |
| `BGE_RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | HuggingFace model ID for the reranker |
| `BGE_DEVICE` | `auto` | Device policy: `auto` / `cuda` / `cpu` |
| `BGE_FP16` | `false` | fp16 precision (GPU only; leave false on CPU) |
| `BGE_M3_MAX_LENGTH` | `8192` | Max token length for encode() calls |
| `BGE_MAX_BATCH_SIZE` | `32` | Max units (texts/pairs) per batch |
| `BGE_MAX_WAIT_MS` | `10` | Batch formation window in milliseconds |
| `BGE_MAX_QUEUE_SIZE` | `8` | Per-op wait-queue capacity (requests); full -> HTTP 503 + Retry-After immediately |
| `BGE_RETRY_AFTER_SECONDS` | `2` | Retry-After advertised on a 503 |
| `BGE_MAX_CONCURRENT` | `0` | Global cap on simultaneous forward passes (embed+rerank). 0 = auto: 1 on CPU, else one per loaded model |
| `BGE_SUB_BATCH_SIZE` | `0` | Texts/pairs per model call; abandoned work is dropped between calls. 0 = auto: 8 on CPU, unsplit elsewhere |
| `BGE_SMALL_REQUEST_MAX_ITEMS` | `4` | Requests this small ride a priority lane ahead of queued bulk batches (0 = off) |
| `BGE_DISCONNECT_POLL_SECONDS` | `0.25` | Client-disconnect poll interval while a request waits |
| `BGE_TORCH_NUM_THREADS` | `0` | Intra-op torch threads (0 = auto) |
| `LOGGING_CONSOLE_LEVEL` | `INFO` | Console log level |
| `LOGGING_LPP_FORMAT` | `ShortFormat` | loggerplusplus format (ShortFormat or DebugFormat) |
| `LOGGING_ENABLE_CONSOLE` | `true` | Enable stdout logging |
| `LOGGING_ENABLE_FILE` | `false` | Enable rotating file logs under `logs/` |

**Disable batching:** set `BGE_MAX_BATCH_SIZE=1` and `BGE_MAX_WAIT_MS=0` for per-request processing
(no wait overhead, useful for debugging or environments where latency matters more than throughput).

## Admission control and abandoned work

- Every inference route polls `request.is_disconnected()` while waiting. A request whose client is
  gone is never started; a queued one is dropped by the worker without running (HTTP 499, unread).
- Inference runs in `asyncio.to_thread`: a forward pass already running cannot be interrupted.
  Cancellation therefore takes effect only at check points: before the first pass and between
  sub-batches (`BGE_SUB_BATCH_SIZE`). A sub-batch is skipped only if all its requests are abandoned.
- A global semaphore (`BGE_MAX_CONCURRENT`) caps forward passes; the bounded per-op queue
  (`BGE_MAX_QUEUE_SIZE`) answers 503 + `Retry-After` immediately when full. `/health` never touches
  the engine.
- Small requests (<= `BGE_SMALL_REQUEST_MAX_ITEMS` texts/pairs) are served before queued bulk
  batches and never coalesced with them. Bulk can wait while small requests keep arriving.
