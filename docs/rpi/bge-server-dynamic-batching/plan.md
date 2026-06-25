# RPI Plan — bge_server dynamic-batching engine

FEATURE: In-process dynamic (micro-)batching for `src/bge_server/`
PHASE: Implementation
Research: `docs/rpi/bge-server-dynamic-batching/research.md` (BUILD decided; Redis excluded).

---

## 0. Architecture decided (5 open questions resolved)

1. **Per-op vs single queue → 3 queues, 3 workers** (dense / sparse / rerank). Independent batching,
   simple scatter. Justified below by the shared-model hazard.
2. **max_length → global** `BGE_M3_MAX_LENGTH` (the TEI contract has no per-request length field).
3. **Rerank fairness → unit-cost batching.** `BGE_MAX_BATCH_SIZE` counts *units*: texts for embed/sparse,
   `(query,passage)` *pairs* for rerank. Each queued item declares its `cost`. A batch accumulates items
   until `Σcost ≥ BGE_MAX_BATCH_SIZE` **or** the wait window elapses. A single item whose `cost` exceeds
   the max is admitted whole and **never split** (FlagEmbedding internally chunks by its own batch_size).
4. **Hand-rolled queue+Future → confirmed** (not the `batched` lib): we need per-item error isolation,
   bounded backpressure, and graceful drain — all owned explicitly.
5. **Verify → concurrent-load test on the GPU image** (see §6).

### ⚠ Added safety decision — single shared model lock
Dense and sparse workers both call the SAME `embed_model` instance; rerank uses `reranker`. Three workers
offloading via `asyncio.to_thread` would run concurrent forward passes on shared torch/tokenizer/CUDA
state → unsafe. Resolution: one shared **`asyncio.Lock` (model_lock)** acquired around EVERY `to_thread`
model call. Batches are *formed* concurrently (good overlap) but *executed* one at a time (safe; a single
GPU serializes anyway, so zero throughput cost). This makes "concurrency=1 on the model" true across all
three ops, not just within one.

### Data flow
```
handler → engine.submit_*(payload)        # creates asyncio.Future, put_nowait on bounded queue, await fut
   per-op BatchQueueWorker._run():         # the only consumers
     drain queue → form batch (Σcost or wait window)
     async with model_lock:                # global serialize
        raw = await asyncio.to_thread(<BgeModelsService method>, flat_inputs, ...)
     scatter raw → fut.set_result(slice) per request   # rerank: re-index 0..n-1 per request
```

---

## New files

### 1. `src/bge_server/libs/batching/models.py`
- `@dataclass(slots=True) BatchItem` — base: `future: asyncio.Future`, `cost: int`.
- `@dataclass(slots=True) EmbedItem(BatchItem)` — `texts: list[str]` (cost = len(texts)).
- `@dataclass(slots=True) RerankItem(BatchItem)` — `query: str`, `texts: list[str]` (cost = len(texts) = pair count).
- `class QueueFullError(Exception)` — raised by `submit_*` when the bounded queue is full (router → 503).

### 2. `src/bge_server/libs/batching/worker.py`
- `class BatchQueueWorker(LoggerClass)` — ONE generic micro-batcher per op.
  - `__init__(self, name, max_batch_size, max_wait_ms, max_queue_size, model_lock, process_fn)`
    - `name` → logger identifier suffix + log tag (`dense`/`sparse`/`rerank`).
    - `process_fn: Callable[[list[BatchItem]], Awaitable[None]]` — op-specific flatten→lock+to_thread→scatter.
    - creates `self._queue = asyncio.Queue(maxsize=max_queue_size)`; `self._task: asyncio.Task | None`.
  - `submit(self, item) -> None` — `try: self._queue.put_nowait((item)) except asyncio.QueueFull: raise QueueFullError`. (Future created by caller/engine; submit just enqueues.)
  - `start(self)` — `self._task = asyncio.create_task(self._run())`.
  - `async stop(self)` — cancel task; drain queue setting `QueueFullError`/`CancelledError` on every pending
    `item.future` (guard `if not fut.done()`), so no awaiting client hangs.
  - `async _run(self)` — the loop: await first item; accumulate until `Σcost ≥ max_batch_size` or
    `max_wait_ms` elapsed (`asyncio.wait_for(queue.get(), remaining)`); `await self._process_fn(batch)`.
    DEBUG log: `f"[{name}] batch: {len(batch)} reqs, {total_cost} units, waited {ms}ms"`.
  - Method order per python.md (dunders → _protected `_run` → public submit/start/stop).

### 3. `src/bge_server/libs/batching/engine.py`
- `class BatchingEngine(LoggerClass)` — composes the 3 workers + the shared lock + the model service.
  - `__init__(self, models: BgeModelsService, max_length, max_batch_size, max_wait_ms, max_queue_size)`
    - `self._model_lock = asyncio.Lock()`
    - builds 3 `BatchQueueWorker`s, each given a bound `_process_dense/_process_sparse/_process_rerank`.
  - `start(self)` / `async stop(self)` — fan out to the 3 workers; INFO logs.
  - **public submit coroutines** (called by router):
    - `async submit_embed_dense(self, texts) -> list[list[float]]`
    - `async submit_embed_sparse(self, texts) -> list[list[dict[str, int|float]]]`
    - `async submit_rerank(self, query, texts) -> list[dict[str, int|float]]`
    - each: build `Future` (via running loop), wrap in item with `cost`, `worker.submit(item)`, `return await fut`.
  - **`_process_*` (protected)** — flatten / lock+to_thread / scatter:
    - dense: `flat = concat item.texts`; `async with lock: vecs = await to_thread(models.encode_dense, flat, max_length)`;
      scatter by per-item text offsets → `fut.set_result(vecs[start:end])`.
    - sparse: same with `models.encode_sparse` → list of dicts sliced by offsets.
    - rerank: `flat_pairs`-equivalent → call `models.compute_rerank_scores` PER nothing — instead add a
      batched method (see service change) that takes a flat `(query, texts)` grouping. Implementation:
      concat all `(query_i, text_ij)`; one `compute_score`; scatter so each request gets
      `[{"index": i, "score": s} for i, s in enumerate(its_scores)]` (**index re-numbered 0..n-1 per request**).
    - error isolation: wrap the lock/to_thread/scatter in try/except; on failure set the exception on every
      future in the batch (`if not fut.done()`), never raise out of `_run`.

### 4. `src/bge_server/libs/batching/__init__.py`
- Export `BatchingEngine`, `QueueFullError`.

### 5. `src/bge_server/tests/unit/test_batching.py` (+ `tests/__init__.py` if needed)
- Mock `BgeModelsService`. Assert: (a) batches form by size, (b) batches form by wait window,
  (c) dense/sparse scatter offsets correct, (d) rerank scatter re-indexes 0..n-1 per request,
  (e) `QueueFullError` when queue full, (f) `stop()` resolves pending futures with an exception (no hang),
  (g) a model-call exception propagates to all futures in that batch only.

---

## Modified files

### 6. `src/bge_server/libs/bge_models/service.py`
- Keep as the model owner. Add ONE method for cross-request rerank batching:
  `compute_rerank_scores_flat(self, pairs: list[list[str]]) -> list[float]` — thin wrapper over
  `reranker.compute_score(pairs, normalize=True)` returning the flat score list (the engine builds the
  pairs + scatters). The existing per-request `compute_rerank_scores` may delegate to it (DRY) or stay.
- `encode_dense` / `encode_sparse` already accept a `list[str]` and `max_length` — reused as-is by the engine.
- Per-call DEBUG logs stay (single model-call timing); engine adds batch-formation DEBUG.

### 7. `src/bge_server/backend/routers/inference/router.py`
- Handlers stop calling `CONTEXT.bge_models.*`; they call the engine and translate backpressure:
  ```python
  texts = InferenceHelpers.as_list(req.inputs)
  if not texts: return []
  try:
      return await CONTEXT.batching_engine.submit_embed_dense(texts)
  except QueueFullError:
      raise HTTPException(status_code=503, detail={"error": "server overloaded"},
                          headers={"Retry-After": "1"})
  ```
  Same shape for `/embed_sparse` (wrap dicts into `SparseToken`) and `/rerank` (wrap into `RerankResult`).
- `@auto_handle_errors` re-raises `HTTPException`, so the 503 passes through unchanged.

### 8. `src/bge_server/backend/lifespan.py`
- Remove the `BGE_MAX_CONCURRENCY` semaphore (superseded). Update `TOTAL_STEPS`.
- After model load: build `CONTEXT.batching_engine = BatchingEngine(CONTEXT.bge_models, …config…)`,
  `CONTEXT.batching_engine.start()`. Add the batching knobs to the ready banner.
- `finally`: `if hasattr(CONTEXT, "batching_engine"): await CONTEXT.batching_engine.stop()` BEFORE
  `bge_models.unload()` (drain in-flight, then free models).

### 9. `src/bge_server/backend/context.py`
- `+ batching_engine: BatchingEngine`. Remove `inference_semaphore`.

### 10. `src/bge_server/config_loader.py`
- Add: `BGE_MAX_BATCH_SIZE` (int, default 32), `BGE_MAX_WAIT_MS` (int, default 10),
  `BGE_MAX_QUEUE_SIZE` (int, default 256). Remove `BGE_MAX_CONCURRENCY`.
- `validate()` unchanged (still guards `BGE_DEVICE`); optionally assert the 3 new ints ≥ 1 / ≥ 0.

### 11. `services/bge_server/.env.example` + `src/bge_server/README.md`
- Document the 3 knobs (and that batching degrades to per-request with `BGE_MAX_BATCH_SIZE=1` +
  `BGE_MAX_WAIT_MS=0` — no separate enable flag needed). Remove `BGE_MAX_CONCURRENCY`.

### 12. `docker-compose.yml`
- Optional: add `--limit-concurrency` to uvicorn? NO — the engine's bounded queue + 503 is the backpressure
  mechanism; leave uvicorn as-is. (Note only.)

---

## Env vars
- `BGE_MAX_BATCH_SIZE=32`  # units per batch (texts for embed/sparse, pairs for rerank)
- `BGE_MAX_WAIT_MS=10`     # batch formation window
- `BGE_MAX_QUEUE_SIZE=256` # bounded per-op queue; full → HTTP 503 + Retry-After
- (removed) `BGE_MAX_CONCURRENCY`

No new deps. No migration. TEI contract frozen. CPU+GPU variants + transformers<5 kept.

---

## Test strategy
- **Unit** (`tests/unit/test_batching.py`, mocked model, pytest-asyncio already in dev deps): batch-by-size,
  batch-by-wait, dense/sparse offset scatter, rerank per-request re-indexing, QueueFull→error,
  graceful-stop resolves futures, batch error isolation.
- **Verify (manual, GPU image, RTX 4050)** — §6.

## 6. Verify step (proves the goal)
1. Build GPU image (`--build-arg TORCH_VARIANT=gpu`), run `--gpus all -e BGE_DEVICE=cuda -e BGE_FP16=true`
   `-e LOGGING_CONSOLE_LEVEL=DEBUG`.
2. **Non-blocking proof**: fire N=20 concurrent `/embed` requests; concurrently poll `/health` and assert it
   keeps returning 200 with low latency DURING inference (today it stalls).
3. **Throughput proof**: compare total wall-time for 50 single-text `/embed` requests issued concurrently
   vs the pre-change serial baseline; expect a clear drop (batches coalesce). Check DEBUG logs show
   batches of >1 forming (`[dense] batch: K reqs, M units`).
4. **Correctness**: `/embed` dim 1024; `/embed_sparse` TEI shape; `/rerank` scores still rank the GPU
   answer top (re-confirm the transformers<5 path); verify rerank indices are 0..n-1 per request.
5. Clean up the test container.

---

## DocForge invariants checklist
- [x] IR canonical — N/A (standalone model host, not a pipeline stage).
- [x] Provider Protocol — N/A (server side; `tei`/`bge_reranker` consumers unchanged; contract frozen).
- [x] Env-flag safety — batching is the serving path; tunable to effectively-off (`BATCH_SIZE=1`,`WAIT_MS=0`)
      instead of a separate flag (documented).
- [x] Migration — none.
- [x] DAG node — N/A.
- [x] No Docker/MinIO refs.

## Risks
- Rerank scatter mis-indexing (must re-number per request) — covered by unit test (d).
- Shared-model concurrency — covered by the single `model_lock` (§0).
- Future leak on disconnect — `if not fut.done()` guards everywhere + stop() drains.
- max_wait too high adds flat latency — default 10 ms, env-tunable.

---

Plan is ready. Respond **GO** to begin implementation or **NO-GO** to revise.
