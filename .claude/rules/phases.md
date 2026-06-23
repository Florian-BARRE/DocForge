---
paths:
  - "src/docforge/libs/**"
  - "src/docforge/backend/**"
  - "src/docforge/frontend/**"
  - "src/docforge/mcp_server.py"
---

# DocForge — Phase File Inventory

Reference file listing every module added or modified per phase. Use to understand where
a concept was introduced or which files are relevant to a given feature.

> **⚠️ Structure refactor (2026-06-19):** `libs/` was reorganized into 6 domain buckets.
> The paths in the per-phase sections below use the original flat names — translate with this map:
>
> | Old flat path | Current bucket path |
> |---|---|
> | `libs/ir/` | `libs/domain/ir/` |
> | `libs/metadata/` (schema) | `libs/domain/metadata/` |
> | `libs/pipeline/pipeline_config.py` | `libs/config/pipeline/` (package) |
> | `libs/admission/`, `libs/config_validation/` | `libs/config/admission/`, `libs/config/validation/` |
> | `libs/providers/` (old flat) | `libs/providers/` (now `libs/capabilities/` renamed back) |
> | `libs/providers/registry.py` | `libs/pipeline/assembly/` |
> | `libs/storage/` | `libs/storage/` (direct, via `libs/data/storage/` interim) |
> | `libs/retrieval/`, `libs/metadata/indexer.py` | `libs/search/hybrid/`, `libs/search/metadata_indexer/`, `libs/search/field_index/` |
> | `libs/pipeline/` (old flat) | `libs/pipeline/` (orchestrator/, stages/, caches/, worker/, assembly/) |
>
> Stage files (s0..s6) are now packages: `pipeline/stages/s0_ingest/core.py`, etc.
> Imports: always `from libs.<bucket>.<module> import …`. See CLAUDE.md for the layer DAG.

---

## P2 — Stage Engine

```
libs/pipeline/fingerprint.py      # blake3 Merkle-DAG compute_fingerprint()
libs/pipeline/node_cache.py       # NodeCache → stage_run table
libs/pipeline/provider_cache.py   # ProviderCallCache → provider_call table
libs/pipeline/engine.py           # StageEngine (replaces PipelineRunner)
libs/pipeline/tasks.py            # arq task run_pipeline_task()
libs/pipeline/worker.py           # arq WorkerSettings + startup/shutdown
arq_worker.py                     # arq CLI entry point
libs/storage/postgres/repositories/job_repo.py
backend/routers/jobs/             # GET /api/v1/jobs/{id}
backend/routers/playground/       # POST /api/v1/playground/run (dry_run)
migrations/versions/002_gin_indexes.py
```

## P3 — S2 Enrichment (OCR/VLM/Chart)

```
libs/providers/chain.py                      # ProviderChain[T] — generic escalation chain
libs/providers/classifier/base.py            # FigureClassifier Protocol + ClassificationResult
libs/providers/classifier/layout_labels.py   # LayoutLabelsClassifier (heuristic pixel stats)
libs/providers/classifier/vit_onnx.py        # VitOnnxClassifier (ONNX ViT, lazy-loaded)
libs/providers/ocr/paddle_ocr.py             # PaddleOcrProvider (local GPU/CPU, cost=0)
libs/providers/ocr/mistral_ocr.py            # MistralOcrProvider (cloud, confidence=1.0)
libs/providers/vlm/openai_compat.py          # OpenAICompatVlmProvider (grounding + chart schema)
libs/pipeline/stages/s2_enrich.py            # S2EnrichStage + S2Result (routing OCR/VLM/chart)
```

## P4 — S4/S5/S6 Chunking + Embedding + Indexing

```
libs/ir/chunk.py                              # Chunk dataclass (atomic retrieval unit)
libs/providers/embed/tei.py                   # TeiEmbedProvider (BGE-M3 TEI HTTP, dense+sparse)
libs/storage/qdrant/client.py                 # QdrantStorageClient (named dense+sparse, upsert)
libs/storage/postgres/repositories/chunk_repo.py  # ChunkRepository (bulk_insert ON CONFLICT DO NOTHING)
libs/pipeline/stages/s4_chunk.py              # S4ChunkStage — structure-aware recursive chunker
libs/pipeline/stages/s5_contextualize.py      # S5ContextualizeStage — title + breadcrumb + body
libs/pipeline/stages/s6_embed_index.py        # S6EmbedIndexStage — BGE-M3 embed + Qdrant upsert
migrations/versions/003_chunks.py             # chunk table + 3 indexes
```

## P5 — Collections API + Hybrid Search

```
libs/retrieval/hybrid_search.py              # HybridSearchService — embed → Qdrant RRF → Postgres
backend/routers/chunks/router.py             # GET /api/v1/chunks/{id}
backend/routers/collections/router.py        # GET /schema, PUT /pipeline, POST /reindex, POST /search
backend/routers/documents/router.py          # GET /markdown + collection_id bug fix
```

## P6 — React UI + MCP Server

```
frontend/src/theme.ts                        # design tokens (dark-first, indigo accent)
frontend/src/App.tsx                         # main orchestrator (state, polling, search, upload)
frontend/src/api/client.ts                   # typed API client
frontend/src/components/Header.tsx           # collection tabs + searchbar
frontend/src/components/DropZone.tsx         # drag-and-drop zone
frontend/src/components/DocumentCard.tsx     # animated status indicators
frontend/src/components/SearchResults.tsx    # ranked chunks with score bar
mcp_server.py                                # FastMCP stdio — 7 tools
.mcp.json                                    # Claude Code MCP config
```

---

## P7a/P7b — Search Pipeline Engine

```
libs/config/pipeline/stages/search_config.py    # SearchConfig, QueryTransformConfig, RerankConfig
libs/config/pipeline/pipeline.py                # PipelineConfig.search field added
libs/config/pipeline/stages/__init__.py         # exports for new search config types

libs/providers/llm/                             # new LLM provider family
  base.py                                       #   LLMProvider Protocol (async generate)
  local/openai_compat.py                        #   LocalLLMProvider (any OpenAI-compat endpoint)
  local/config.py                               #   LocalLLMConfig @register("llm"), id="local_llm"
  external/openai.py                            #   OpenAILLMProvider
  external/config.py                            #   OpenAILLMConfig @register("llm"), id="openai_llm"

libs/providers/rerank/                          # new Rerank provider family
  base.py                                       #   RerankProvider Protocol (async rerank)
  local/bge_reranker.py                         #   BgeRerankProvider (TEI /rerank endpoint)
  local/config.py                               #   BgeRerankerConfig @register("rerank"), id="bge_reranker"
  external/cohere.py                            #   CohereRerankProvider (Cohere Rerank v2 API)
  external/config.py                            #   CohereRerankConfig @register("rerank"), id="cohere_rerank"

libs/search/pipeline/                           # new search pipeline package
  engine.py                                     #   SearchPipelineEngine (wraps HybridSearchService)
  stages/q_transform.py                         #   QueryTransformStage (rewrite/HyDE/multi_query)
  stages/rerank.py                              #   RerankStage (cross-encoder reranking)

libs/pipeline/assembly/registry.py              # added build_search_pipeline() method
backend/routers/collections/documents/search/router.py  # routes now use SearchPipelineEngine
config/runtime/runtime_config.py                # BGE_RERANKER_URL/BATCH_SIZE, COHERE_API_KEY, LLM_*
services/docforge/.env                          # reranker + LLM env vars (commented examples)
docker-compose.yml                              # reranker service (TEI CPU, BAAI/bge-reranker-v2-m3)
docker-compose.dev.yml                          # reranker port 10027:80
```

## Key decisions per phase

### P2
- StageEngine replaces PipelineRunner; double cache = NodeCache (DAG) + ProviderCallCache (provider calls)
- blake3 Merkle-DAG fingerprint for deterministic cache keys
- dry_run skips S4/S5/S6 entirely — no writes

### P3
- S2 is opt-in: `S2_ENRICH_ENABLED=false` by default
- Routing table: DECORATIVE→skip; SCANNED_TEXT→OCR; CHART→OCR+VLM+chart-to-data; DIAGRAM→OCR+VLM; PHOTO→VLM
- Budget gate: `ENRICH_MAX_BUDGET_USD=0.0` = unlimited

### P4
- Chunk UUID v5 derived from `(doc_id, block_ids, config_hash)` — stable, idempotent
- S5 embed_text = `{title}\n{H1 > H2 breadcrumb}\n{body}`
- S4/S5/S6 NOT in NodeCache — rely on Postgres/Qdrant idempotency instead

### P5
- Hybrid search: TEI embed → Qdrant RRF (FusionQuery) → Postgres hydration
- `collection_id` bug: was silently None in enqueue_job() — fixed in documents/router.py
- `CONTEXT.retrieval` is `HybridSearchService | None` (None when S6_ENABLED=false)

### P6
- UX: zero-training — unified single-screen, collections as tabs, search always visible
- Design: dark-first (`#0d0f18` base, `#6366f1` indigo accent), no external UI library
- MCP: FastMCP stdio — 7 tools (list_collections, list_documents, get_document, search_documents,
  ingest_document, create_collection, reindex_collection)
- Static files: FastAPI mounts `frontend/dist` at `/` only if directory exists

### P7a/P7b
- Search config: `SearchConfig` added to `PipelineConfig` — fully backward-compatible (strategy="none", rerank.enabled=False = identical to pre-P7 behavior)
- Embed provider always auto-derived from `pipeline.embed.chain[0]` — never configurable in SearchConfig
- `SearchPipelineEngine` wraps `HybridSearchService` — no modifications to `HybridSearchService` itself
- RRF fusion (`k=60`) used when multi_query produces N variants: `score(d) = sum_i 1/(k + rank_i(d))`
- HyDE: LLM generates a hypothetical passage, embeds it, retrieves top-k, then re-ranks if enabled
- Graceful fallback: LLM failure in query transform falls back to `[query]` (original unchanged)
- Reranker separate TEI container (port 10027 in dev) — different model from embed TEI (port 10025)
- `build_search_pipeline(pipeline_dict, retrieval)` on `ProviderRegistry` — retrieval passed in, not stored (avoids circular ownership with `HybridSearchService`)

---

## Resource/Job/Monitoring chantier — Brique A (Observability)

> Roadmap of 5 bricks (A observability → C real-time SSE → D resources → B mass ingestion →
> E dashboard): `docs/superpowers/specs/2026-06-23-resource-job-monitoring-roadmap-design.md`.
> Brique A RPI docs: `docs/rpi/observability-brick-a/{research,plan,implementation}.md`.

```
libs/observability/                          # NEW L2 bucket (imports only domain/config/providers/storage)
  queue/introspector.py                      #   QueueIntrospector — read-only arq (ZCARD/status/SCAN)
  metrics/{system,gpu,collector}.py          #   psutil + pynvml gauges (GPU fail-soft on CPU image)
  heartbeat/{models,writer,reader}.py        #   WorkerHeartbeat + TTL'd Redis writer/reader
  events/{channels,publisher}.py             #   single docforge:events pub/sub channel
libs/pipeline/worker/heartbeat.py            # WorkerHeartbeatLoop (background task per worker)
backend/routers/jobs/                        # GET /api/v1/jobs, /{id} (+live arq status), POST /{id}/cancel
backend/routers/monitoring/                  # GET /api/v1/monitoring/{queue,workers,overview,discovery}
migrations/versions/009_job_observability.py # +job: worker_id, started_at, finished_at, attempt, current_stage, progress
libs/storage/postgres/repositories/job_repo.py  # +list_jobs/count_by_status/count_finished_since/mark_running/mark_finished/update_progress
libs/pipeline/worker/{worker,worker_bootstrap,tasks}.py  # max_jobs, allow_abort_jobs, worker_id, heartbeat, progress_cb, events
libs/pipeline/orchestrator/core.py           # optional progress_cb at stage boundaries (telemetry-only)
backend/{context,lifespan,app}.py            # wiring (queue_introspector/heartbeat_reader/event_publisher)
config/runtime/runtime_config.py             # WORKER_MAX_JOBS, WORKER_ALLOW_ABORT, OBS_HEARTBEAT_*, OBS_METRICS_ENABLED
```

### Key decisions — Brique A
- New deps: `psutil`, `nvidia-ml-py` (pure-python, safe on CPU-only image). `sse-starlette` deferred to brique C.
- Dual store: durable job state in Postgres; ephemeral heartbeats/gauges in Redis (TTL ≈ 3× interval).
- Single event channel `docforge:events` (typed payload). A only **publishes**; brique C subscribes via SSE.
- No `SCAN` in hot path: depth=`ZCARD`, running counts=Postgres, workers=heartbeat keys (scalable to 1000+).
- `progress_cb` is the sole L3 touch — optional, telemetry-only, failures swallowed; not a DAG node.
- arq abort wired via `allow_abort_jobs=True` + existing `_job_id=str(job_uuid)`; cancel endpoint top-level.
- `mark_running`/`mark_finished` are job STATE (fail the job on error); event publishes are best-effort.
