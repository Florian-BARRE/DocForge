# RPI Implementation — bge_server dynamic-batching engine

Status: **DONE & VERIFIED** (2026-06-25). Plan: `plan.md`. Research: `research.md`.

## Files created
- `src/bge_server/libs/batching/models.py` — `BatchItem`/`EmbedItem`/`RerankItem` (slots, `future`+`cost`); `QueueFullError`.
- `src/bge_server/libs/batching/worker.py` — `BatchQueueWorker(LoggerClass)`: bounded `asyncio.Queue`,
  `_run` batch-formation loop (Σcost ≥ max_batch_size OR max_wait_ms window), `submit`/`start`/`stop` with drain.
- `src/bge_server/libs/batching/engine.py` — `BatchingEngine(LoggerClass)`: 3 workers (dense/sparse/rerank)
  + ONE shared `asyncio.Lock` held across every `asyncio.to_thread` model call; `submit_embed_dense/_sparse/_rerank`.
- `src/bge_server/libs/batching/__init__.py` — exports `BatchingEngine`, `QueueFullError`.
- `src/bge_server/tests/unit/test_batching.py` (+ `tests/__init__.py`) — 8 tests, all pass.

## Files modified
- `backend/routers/inference/router.py` — handlers `await CONTEXT.batching_engine.submit_*`; `QueueFullError → HTTP 503 + Retry-After`.
- `backend/lifespan.py` — removed `BGE_MAX_CONCURRENCY` semaphore; build+start engine after model load; `await engine.stop()` before `unload()`; ready banner shows batching knobs.
- `backend/context.py` — `+ batching_engine`, removed `inference_semaphore`.
- `config_loader.py` — `+ BGE_MAX_BATCH_SIZE=32 / BGE_MAX_WAIT_MS=10 / BGE_MAX_QUEUE_SIZE=256` (validated ≥); removed `BGE_MAX_CONCURRENCY`. (`BGE_TORCH_NUM_THREADS` kept.)
- `libs/bge_models/service.py` — `+ compute_rerank_scores_flat(pairs)`; torch-thread cap comment updated (single serialized call → all cores; `_max_concurrency` is 1 by design).
- `services/bge_server/.env.example`, `README.md` — documented the 3 knobs (batch_size=1+wait_ms=0 ≈ off).

## Key design (as built)
- In-process `asyncio.Queue` (NOT Redis). 3 op queues, 1 worker each = only callers of the model.
- Shared `model_lock` serializes execution (dense+sparse share `embed_model`) while batch *formation* overlaps.
- Cost units: texts (embed/sparse) / pairs (rerank). Rerank flattens pairs across requests, scatters,
  **re-indexes results 0..n-1 per request**. Per-item error isolation; bounded queue → 503; graceful drain on stop.

## Env vars
`BGE_MAX_BATCH_SIZE=32`, `BGE_MAX_WAIT_MS=10`, `BGE_MAX_QUEUE_SIZE=256`. Removed `BGE_MAX_CONCURRENCY`.
No new deps, no migration, TEI contract frozen, CPU+GPU variants + transformers<5 kept.

## Tests
- Unit: `cd src/bge_server && uv run --extra cpu --group dev pytest tests/unit -q` → **8 passed**.

## Code review
- code-reviewer: **APPROVED WITH SUGGESTIONS**, all 10 correctness checks PASS. Suggestions applied:
  added logging to `worker._run` last-resort net (`logger.exception`) and `worker.stop` task-await
  (`logger.warning`); refreshed the stale `BGE_MAX_CONCURRENCY` comment in `service.py`.

## GPU Verify (RTX 4050, image `docforge-bge-server:gpu` 9.47 GB, cuda + fp16)
- Boot: 3 workers + engine started; `policy: cuda -> device: cuda`; `batching: max_batch=64, wait_ms=15`.
- **Throughput**: 50 concurrent single-text `/embed` → **1108 ms** total (vs ~15 s serial). Batches formed:
  23 / 11 / 8 / 4 / 3 reqs (DEBUG `[dense] batch: N reqs, N units, waited ~15ms`).
- **Non-blocking**: `/health` during the 50-req burst → **HTTP 200 in 104 ms** (event loop free).
- **Correctness**: `/embed` 1024-dim; `/embed_sparse` TEI `[{index,value}]`; `/rerank` ranks GPU answer top
  (0.967 vs 1.6e-5) with indices re-numbered 0..n-1 per request; `compute_rerank_scores_flat` used (cost=pairs).

## Follow-ups (optional)
- Add a unit test asserting the shared-lock serialization invariant (currently proven only via GPU verify).
- Consider per-op `max_batch_size`/`max_wait_ms` if rerank vs embed need different windows.
