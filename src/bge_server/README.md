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
| GET  | `/health` | -- | `{"status":"ok","embed_model":"...","rerank_model":"..."}` |
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

```
src/bge_server/
  entrypoint.py          # uvicorn target (module-level app); wires CONTEXT + creates FastAPI app
  config_loader.py       # BgeServerConfig(EnvConfigLoader) -- all env vars + logging setup
  pyproject.toml         # uv-managed dependencies (FlagEmbedding, fastapi, uvicorn, loggerplusplus...)
  uv.lock                # locked dependency graph
  Dockerfile             # 2-stage uv build; CPU torch installed from PyTorch wheel index
  libs/
    bge_models/
      service.py         # BgeModelsService(LoggerClass) -- loads/unloads both models, encode/rerank
      device.py          # DeviceResolver -- BGE_DEVICE policy -> concrete device + fp16 gate
    batching/
      models.py          # BatchItem/EmbedItem/RerankItem dataclasses + QueueFullError
      worker.py          # BatchQueueWorker(LoggerClass) -- one generic micro-batcher per op
      engine.py          # BatchingEngine(LoggerClass) -- owns 4 workers + shared model_lock
  backend/
    app.py               # create_app() -- FastAPI factory, registers routers
    context.py           # CONTEXT static service locator (CONFIG + bge_models + batching_engine)
    lifespan.py          # lifespan() -- banner + config log + model load + engine start/stop
    libs/utils/
      error_handling.py  # @auto_handle_errors decorator for all routes
    routers/
      health/            # GET /health
      inference/         # POST /embed, /embed_sparse, /embed_colbert, /rerank (through batching engine)
  tests/unit/
    test_batching.py     # unit tests for the batching engine (mocked models, no torch)
services/bge_server/
  .env.example           # all env var defaults
```

## Build — two torch variants

The Dockerfile supports two mutually exclusive torch variants selected at build time via
`--build-arg TORCH_VARIANT`. The default is `cpu`.

| Variant | Torch version | nvidia-* libs | Approximate image size | CUDA available |
|---|---|---|---|---|
| `cpu` (default) | 2.12.1+cpu | none | ~2 GB | no |
| `gpu` | 2.6.0+cu124 | yes (cu12-*) | ~9.5 GB | yes (with --gpus) |

```bash
# CPU variant (default) — used by docker compose build, no flags needed:
docker compose build bge_server

# Or equivalently with explicit arg:
docker build -f src/bge_server/Dockerfile -t docforge-bge-server:latest src

# GPU variant (opt-in) — CUDA 12.4, compatible with RTX 40xx (Ada, compute 8.9):
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

Already wired in `docker-compose.yml` as the `bge_server` service (port 10026, volume `bge_models`).
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
| `BGE_MAX_QUEUE_SIZE` | `256` | Per-op queue capacity; full -> HTTP 503 + Retry-After |
| `BGE_TORCH_NUM_THREADS` | `0` | Intra-op torch threads (0 = auto) |
| `LOGGING_CONSOLE_LEVEL` | `INFO` | Console log level |
| `LOGGING_LPP_FORMAT` | `ShortFormat` | loggerplusplus format (ShortFormat or DebugFormat) |
| `LOGGING_ENABLE_CONSOLE` | `true` | Enable stdout logging |
| `LOGGING_ENABLE_FILE` | `false` | Enable rotating file logs under `logs/` |

**Disable batching:** set `BGE_MAX_BATCH_SIZE=1` and `BGE_MAX_WAIT_MS=0` for per-request processing
(no wait overhead, useful for debugging or environments where latency matters more than throughput).
