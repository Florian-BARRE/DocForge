# RPI Research — bge_server dynamic-batching redesign

> Goal: make `src/bge_server/` reactive and non-blocking under concurrent load, with
> TEI/vLLM-style **dynamic batching**, while preserving the TEI-compatible HTTP contract.
> Date: 2026-06-25.

---

## FEATURE
TEI/vLLM-style **dynamic (micro-)batching** inference engine for the local BGE model host,
so HTTP handlers never block the event loop and a single GPU is saturated by batched calls.

## COMPONENT AFFECTED
`src/bge_server/` only (standalone model host, OUTSIDE the docforge layer DAG). No S0–S6
pipeline stage, no docforge migration. Downstream consumers (`tei` embed provider +
`bge`/`bge_reranker` rerank providers in `common_libs/providers`) must keep working unchanged.

---

## DECISION: BUILD (not adopt) — evidence

The decisive requirement is **BGE-M3 native sparse `lexical_weights`** (`{token_id: weight}`),
which DocForge hybrid search depends on. No off-the-shelf batching server produces it cleanly:

| Server | Dense | **Sparse (lexical_weights)** | Rerank | Dyn. batch | 6 GB fit / CPU | Verdict |
|---|---|---|---|---|---|---|
| **Homemade (current)** | ✅ | ✅ FlagEmbedding native | ✅ | ❌ (this project) | ✅ / ✅ | keep + add batching |
| **Infinity** (`michaelfeil/infinity`, MIT, v0.0.77) | ✅ `/embeddings` | ❌ **no sparse type at all** (issue #146 open ~2 yrs) | ✅ `/rerank` | ✅ (`--batch-size`, def 32) | ✅ / ✅ | NO-GO (loses hybrid) |
| **TEI** (HF, Apache-2.0, v1.9.3) | ✅ Candle (old ONNX crash fixed) | ❌ **SPLADE-only → HTTP 424 for BGE-M3** (XLM-R custom head ≠ MaskedLM) | ✅ `/rerank` exact `[{index,score}]` | ✅ | ✅ / ✅ | NO-GO for sparse |
| **vLLM** (Apache-2.0, v0.10.x/0.11) | ✅ `/v1/embeddings` | ⚠️ raw vocab logits via `/pooling token_classify` only — **NOT** lexical_weights; must reimplement ReLU/max-dedup | ✅ `/score`,`/rerank` (`relevance_score`) | ✅✅ | ⚠️ tight on 6 GB / weak CPU | NO-GO (reimpl + heavy) |

**Conclusion:** keep the FlagEmbedding server (only one-process source of dense + native sparse +
rerank behind one contract) and add an in-process async batching engine. Adopting anything would
require running a SECOND service just for sparse — strictly worse than today.

> Fallback split (NOT recommended now, noted for the future): if sparse is ever decoupled, TEI is a
> clean drop-in for dense+rerank (rerank contract is byte-identical), keeping a thin FlagEmbedding
> sidecar for sparse only.

---

## DESIGN (the build)

### Architecture — queue + future micro-batcher
HTTP handlers stop calling the model directly. Instead:
1. Handler builds an `asyncio.Future`, puts `(payload, future)` on a **bounded** `asyncio.Queue`,
   then `await`s only its own future. Event loop stays free.
2. A **single background worker** coroutine (started in `lifespan`, the ONLY caller of the model):
   - `await` the first queued item, then drain up to `BGE_MAX_BATCH_SIZE` items OR until
     `BGE_MAX_WAIT_MS` elapses (`asyncio.wait_for` on subsequent `queue.get()`).
   - Form ONE batch, run the **blocking** model call via `await asyncio.to_thread(...)`
     (keeps the loop free; single consumer ⇒ model called by one thread at a time = safe).
   - **Scatter** the batched output back to each request's future by per-request slice/offset.
3. **One queue per operation** (dense / sparse / rerank) so tensors of different ops never mix.

### How each op batches (confirmed against FlagEmbedding 1.4.0 source)
- **dense**: concat all texts → `model.encode(texts, return_dense=True)['dense_vecs']`
  → `(ΣN, 1024)` numpy → split by request text-count offsets.
- **sparse**: same with `return_sparse=True` → `lexical_weights` (list of `{token_id(str): float}`)
  → split by offsets → reshape to TEI `[{index:int, value:float}]` (existing helper).
- **rerank**: flatten every `(query, passage)` pair across all queued requests into ONE flat list
  → `reranker.compute_score(all_pairs, normalize=True)` → scatter the flat score list back by each
  request's pair count. **Confirmed safe**: compute_score scores each pair independently (no cross-row
  state), so mixing pairs from different queries in one call is correct.

### FlagEmbedding facts the engine relies on
- `encode` already internally batches (length-sorted, `batch_size` default **256**) and restores order;
  `compute_score` accepts a flat pair list and batches internally too.
- **Thread-safety**: a single model instance is NOT documented thread-safe (Rust tokenizer + shared
  torch/CUDA state). The single-consumer worker (concurrency=1 on the model) sidesteps this entirely.
  Do NOT fan `asyncio.to_thread` to the same model from many handlers (default executor = many threads).
- **Single-device only**: pass `devices=` as a single device (e.g. `"cuda"`/`"cpu"`, already the case)
  so FlagEmbedding stays on the single-device path and does NOT spawn a `spawn` multiprocess pool
  (which would re-load the model + fight the event loop / CPU quota in-container).

### Correctness requirements (must be in the plan)
- **Per-item error isolation**: validate per item before batching; on batch failure set the exception
  only on affected futures; guard `if not fut.done()` (client may have disconnected). One bad item
  must never poison the whole batch.
- **Backpressure**: bounded queue; when full return **HTTP 503 + Retry-After** (or await to apply
  backpressure). Cap max in-flight items.
- **Graceful shutdown** (lifespan teardown): stop intake, drain or cancel pending futures so no client
  hangs; `try/finally` + `hasattr` guards (matches current `lifespan.py`).
- **Latency/throughput knob**: `BGE_MAX_WAIT_MS` (small 5–30 ms) trades p50 latency for throughput.

### Queue backing — IN-PROCESS asyncio.Queue, NOT Redis (resolved)
The batching queue MUST be an in-memory `asyncio.Queue`, never Redis. This is a DIFFERENT queue from
the stack's Redis: Redis+arq is the docforge **worker's durable ingestion JOB queue** (S0–S6, cross-
process, retries). The bge_server batching queue is ephemeral, request-scoped micro-batching of
in-flight HTTP calls. Redis is wrong here because: (1) the batch window is ~10 ms — a Redis RTT +
(de)serialize on the hot path defeats the gain; (2) each request holds a live `asyncio.Future` in THIS
process — a Future can't be resolved across the network, so Redis can't wake the waiting coroutine;
(3) payloads (texts, 1024-dim vectors) are large — pushing them through Redis adds serialize cost +
memory pressure; (4) bge_server is a standalone pure-HTTP model host OUTSIDE the layer DAG (no Postgres/
Redis/S3 dependency today) — adding Redis would break that. The engine batches requests arriving from
BOTH the worker (ingestion) AND the app (query-time) at the HTTP boundary — that's why it lives in
bge_server, not in a shared Redis.

### Library choice
Hand-rolled queue+future batcher (best fit: pure asyncio, lives in `CONTEXT`/`lifespan`, uses
loggerplusplus, single-consumer = thread-safe by construction, ~150 LOC). Optional fallback:
`batched` (mixedbread) drop-in decorator. Reject LitServe/mosec/Ray Serve — they replace the whole
serving layer / pull heavy runtimes, conflicting with the fastapi.md structure.

---

## NEW FILES (proposed — for plan to refine)
- `src/bge_server/libs/batching/engine.py` — `BatchingEngine` (LoggerClass): per-op queues + worker
  loop + scatter; `submit_embed_dense/sparse/rerank()` coroutines returning per-request results.
- `src/bge_server/libs/batching/models.py` — internal `BatchItem`/request dataclasses (if needed).
- `src/bge_server/libs/batching/__init__.py`

## MODIFIED FILES
- `src/bge_server/backend/routers/inference/router.py` — handlers call
  `await CONTEXT.batching_engine.submit_*` instead of `CONTEXT.bge_models.*` directly.
- `src/bge_server/backend/lifespan.py` — start/stop the batch worker(s); the existing
  `BGE_MAX_CONCURRENCY` semaphore is SUPERSEDED by the engine (remove or repurpose).
- `src/bge_server/backend/context.py` — add `batching_engine: BatchingEngine`.
- `src/bge_server/config_loader.py` — add batching env vars.
- `src/bge_server/libs/bge_models/service.py` — keep as the model owner; the engine calls its
  `encode_dense/encode_sparse/compute_rerank_scores` (which already exist) inside `to_thread`.
- `services/bge_server/.env.example`, `README.md` — document new knobs.
- `docker-compose.yml` — `--limit-concurrency` on uvicorn optional (engine handles backpressure).

## NEW ENV VARS (proposed)
- `BGE_MAX_BATCH_SIZE=32` — max items coalesced per forward pass.
- `BGE_MAX_WAIT_MS=10` — batch formation window.
- `BGE_MAX_QUEUE_SIZE=256` — bounded queue (backpressure → 503 when full).
- (Retire/repurpose `BGE_MAX_CONCURRENCY` — the engine's single worker replaces it.)

## NEW DEPENDENCIES
None required (pure asyncio). Optional: `batched` if not hand-rolling.

## MIGRATION
None (standalone service, no DB).

## KEY CONSTRAINTS
- TEI contract FROZEN: `/embed → [[float]]`, `/embed_sparse → [[{index,value}]]`,
  `/rerank → [{index,score}]`, `/health`. `tei` + `bge_reranker` providers unchanged.
- Per-collection `base_url` config (no `.env` for provider URLs). loggerplusplus everywhere;
  python.md/fastapi.md structure; ASCII-only log strings (`->`).
- Keep BOTH CPU and GPU build variants (cpu / cu124). 6 GB VRAM (RTX 4050), fp16.
- transformers pinned `<5` (FlagReranker breaks on 5.x) — keep.
- Single GPU ⇒ inference is physically serial anyway; batching wins on THROUGHPUT + the event loop
  staying responsive, not on parallel model calls.

## OPEN QUESTIONS (for plan / GO-NO-GO)
1. **Per-op vs single queue**: 3 dedicated queues+workers, or one worker tagging by op? (3 queues =
   simpler scatter, but 3 background tasks. Lean: 3 queues, 1 worker each — clean.)
2. **max_length per request**: BGE_M3_MAX_LENGTH is global; if requests in a batch want different
   truncation, batch by max (current behavior). OK to keep global? (Yes — contract has no per-request
   max_length field.)
3. **Rerank fairness**: a single huge rerank request (many candidates) can dominate a batch window.
   Cap pairs-per-batch separately from items-per-batch? (Probably `BGE_MAX_BATCH_SIZE` counts pairs
   for rerank, texts for embed.)
4. **`batched` lib vs hand-rolled**: confirm hand-rolled (recommended) — gives error-isolation +
   shutdown control the plan needs.
5. **Verify** plan must re-run the GPU concurrency test (N parallel clients) to prove non-blocking +
   throughput gain, and re-confirm /rerank correctness (the transformers<5 regression).

## SOURCES
- Infinity: github.com/michaelfeil/infinity (README supported-models "no sparse"; issues #146/#294;
  primitives.py has no sparse type), Docker Hub michaelf34/infinity (CUDA ~4.5 GB, CPU ~0.7 GB), MIT v0.0.77.
- TEI: github.com/huggingface/text-embeddings-inference v1.9.3; `/embed_sparse` SPLADE-only (Bert/
  DistilBert MaskedLM) → 424 for BGE-M3; `/rerank → [{index,score}]`. deepwiki pooling-strategies.
- vLLM: docs.vllm.ai pooling/specific_models (BGE-M3 sparse only via `/pooling token_classify` raw
  logits), scoring (`relevance_score`/`results`), issue #15384/PR #14526; Apache-2.0 v0.10.x/0.11.
- FlagEmbedding 1.4.0: AbsEmbedder/M3Embedder source (encode batch_size=256 length-sorted; dense_vecs
  (N,1024); lexical_weights list-of-dict; single-device branch avoids spawn pool); AbsReranker
  compute_score flat-pairs mixing safe.
- Pattern: FrancescoSaverioZuppichini/dynamic-batching-asyncio; mixedbread `batched`; LitServe/mosec/
  Ray Serve `@serve.batch` (rejected as too heavy).
