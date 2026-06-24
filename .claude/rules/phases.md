---
paths:
  - "src/docforge/libs/**"
  - "src/docforge/backend/**"
  - "src/docforge/frontend/**"
  - "src/docforge_mcp/**"
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
mcp_server.py                                # FastMCP stdio — 7 tools (SUPERSEDED → moved to src/docforge_mcp/ in P8)
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

---

## Resource/Job/Monitoring chantier — Brique C (Real-time SSE)

> Build order A→C→D→B→E. RPI docs: `docs/rpi/observability-brick-c/{research,plan,implementation}.md`.
> Push model replacing the Documents tab's 2 s polling. Brique A already publishes typed events on
> `docforge:events`; brique C subscribes once per backend process and fans out to browsers via SSE.

```
libs/observability/events/broadcaster.py     # NEW EventBroadcaster — 1 dedicated Redis pubsub sub →
                                             #   per-client bounded asyncio.Queue fan-out (drop-oldest);
                                             #   _run self-heals on drop (capped exp backoff)
libs/observability/events/{__init__,publisher}.py  # export EventBroadcaster; stage_progress +collection_id/document_id
libs/pipeline/worker/tasks.py                # _progress_cb forwards collection_id/document_id
backend/libs/utils/sse.py                    # NEW SseHelpers — stream(broadcaster, keepalive, predicate)
                                             #   + collection_predicate(id); SSE routes omit response_model
backend/libs/utils/__init__.py              # export SseHelpers
backend/context.py                           # +event_broadcaster: EventBroadcaster
backend/lifespan.py                          # TOTAL_STEPS=9; start broadcaster step 7; stop() in finally
backend/routers/monitoring/{router,helpers}.py  # GET /stream (global) + discovery advertises stream_endpoint
backend/routers/collections/documents/router.py # GET /stream (collection-scoped, BEFORE /{document_id})
config/runtime/runtime_config.py             # SSE_KEEPALIVE_SECONDS=15, SSE_CLIENT_QUEUE_MAXSIZE=100
services/docforge/.env                       # same two SSE vars
frontend/src/api/client.ts                   # streamCollectionDocuments / streamMonitoring (EventSource)
frontend/src/components/documents/DocumentsTab.tsx  # EventSource (job.updated+stage.progress) debounced
                                             #   refetch + polling fallback torn down once events resume
tests/unit/{test_event_broadcaster,test_sse_helpers}.py  # NEW fan-out/predicate units
tests/unit/test_observability_events.py      # stage_progress shape + scope enrichment
tests/api/monitoring/test_monitoring.py      # discovery asserts wired stream endpoint
pyproject.toml                               # +sse-starlette
```

### Key decisions — Brique C
- New dep: `sse-starlette` (deferred from A). No migration.
- ONE `EventBroadcaster` per process with its OWN Redis connection — a subscribe-mode connection
  cannot issue other commands, so never reuse the arq pool. One sub serves N tabs; multi-instance
  backends each subscribe (pub/sub delivers to all).
- Pub/sub has no replay → clients snapshot-then-stream (REST snapshot + SSE deltas).
- `stage.progress` enriched with collection_id/document_id (Option A) so the scoped stream can filter
  without resolving job→collection in the broadcaster (keeps it domain-agnostic).
- SSE routes keep `@auto_handle_errors` but OMIT `response_model` (a live stream is not a Pydantic
  model) — documented inline. Collection `/stream` MUST precede `/{document_id}` (FastAPI matches in
  declaration order, else "stream" is captured as a doc id).
- Back-pressure: per-client `asyncio.Queue(maxsize=SSE_CLIENT_QUEUE_MAXSIZE)`, drop-oldest on overflow.
- `_run` self-heals a dropped Redis subscription (browser→backend SSE link stays open, so the
  frontend `onerror` fallback can't see a backend→Redis drop); fan-out snapshots the subscriber set.
- Frontend: native `EventSource` (auto-reconnect), debounced refetch, polling fallback on `onerror`
  that is torn down once SSE events resume (avoids permanent double-fetch).

---

## Resource/Job/Monitoring chantier — Brique D (Resource management)

> Build order A→C→**D**→B→E. RPI docs: `docs/rpi/resource-brick-d/{research,plan,implementation}.md`.
> Enqueue-time back-pressure gate — the mechanism Brique B (wave-based mass ingestion) relies on.
> NEW sibling of the config-time `AdmissionValidator`: this gate asks "can we accept MORE load?".

```
backend/libs/admission/                      # NEW backend lib (sibling of config-time AdmissionValidator)
  admitter.py                                #   ResourceAdmitter(LoggerClass) — pure evaluate() + fail-soft admit()
  models.py                                  #   AdmissionDecision / AdmissionSnapshot / ResourceLimits (frozen)
backend/routers/collections/limits/          # NEW sub-router GET/PUT /collections/{id}/limits (+ live usage)
  {router,models,__init__}.py
libs/providers/device/snapshot.py            # NEW DeviceSnapshot frozen gauge
libs/providers/device/manager.py             # +snapshot() read-only gauge (per-capability resolved device)
backend/routers/collections/documents/router.py  # ingest gate: 429 capacity / 409 budget, after admissibility+dedup
backend/routers/monitoring/{models,helpers,router}.py  # GET /monitoring/resources + discovery 'resources' panel
backend/{app,context,entrypoint,lifespan}.py # limits_router wiring + resource_admitter injection
libs/storage/postgres/models/collection.py   # +max_in_flight INT, budget_cap_usd FLOAT (nullable)
libs/storage/postgres/repositories/collection_repo.py  # +update_limits()
libs/storage/postgres/repositories/job_repo.py         # +sum_budget_by_collection()
config/runtime/runtime_config.py             # ADMISSION_ENABLED / MAX_QUEUE_DEPTH / MAX_IN_FLIGHT_GLOBAL
services/docforge/.env                       # same 3 ADMISSION_* vars (commented, 0 = unlimited)
migrations/versions/010_collection_limits.py # +collection per-collection limit columns (009 → 010)
tests/unit/{test_resource_admitter,test_device_snapshot}.py
tests/api/collections/limits/test_collection_limits.py
tests/api/{collections/documents/test_documents,monitoring/test_monitoring,conftest}.py  # 429 / resources / wiring
```

### Key decisions — Brique D
- **Sibling not extension**: document-admissibility (415/413/422) runs first, then resource-admission
  (429/409), and only AFTER the duplicate short-circuit — a harmless re-upload is never throttled.
- **Pure core / I/O shell**: `evaluate(snapshot, limits)` is pure & unit-tested as a decision matrix;
  `admit(*, session, collection, queue_introspector, job_repo)` does the I/O with injected collaborators.
- **Fail-soft**: any introspection error (Redis/Postgres down) → ADMIT + warn. Back-pressure must
  never become a new way to drop ingestion.
- **Precedence**: budget (409) checked before capacity (429).
- **Sentinels**: global int caps `0` = unlimited; per-collection caps `None` = no cap. A *zero*
  per-collection cap is rejected at the API boundary (`ge=1`/`gt=0`) — it would freeze the collection,
  and "unlimited" is already null.
- **Hot-path cheap**: backlog=`ZCARD`, running/spend=indexed Postgres COUNT/SUM — no `SCAN`.
- **Limits as a dedicated sub-resource** (GET/PUT), NOT config merge-patch: keeps resource policy out
  of the pipeline blob (migration-010 columns) so editing a limit never triggers reindex semantics.
- **No async resource**: `resource_admitter` built in `entrypoint.py` wiring (not lifespan), no finally
  guard needed — collaborators passed per-call.
- **Device gauge**: `DeviceManager.snapshot()` → frozen `DeviceSnapshot` feeds `/monitoring/resources`;
  VLM skips CPU by design → resolves to `remote` on a CPU-only host.

---

## P8 — Standalone MCP server (full REST surface)

> Separate minimal app `src/docforge_mcp/` — a PURE HTTP client of the DocForge API exposing the
> whole REST surface as MCP tools, so any LLM/chatbot drives DocForge without a dedicated app.
> Replaces the old 7-tool `src/docforge/mcp_server.py` (deleted). RPI: `docs/rpi/mcp-full-surface/plan.md`.

```
src/docforge_mcp/
  entrypoint.py                  # name aligned w/ docforge; dispatches MCP_TRANSPORT (stdio | streamable-http)
  config_loader.py               # McpConfig(EnvConfigLoader) — self-contained (NOT docforge RUNTIME_CONFIG)
  pyproject.toml + uv.lock       # 6 deps only: mcp>=1.9.0, httpx, uvicorn, starlette, loggerplusplus, configplusplus
  Dockerfile                     # 2-stage uv build, ~150 MB (none of the ML stack)
  libs/
    auth.py                      # StaticBearerAuthMiddleware (401 on bad/absent Bearer token)
    server.py                    # build_mcp(sdk) + build_http_app(mcp, config) (streamable_http_app + middleware)
    sdk/                         # DocForge SDK — typed HTTP client, reusable alone, no domain import
      transport.py               #   DocForgeTransport (httpx get/post/delete/upload/get_bytes)
      client.py                  #   DocForgeClient — composes the 11 sub-APIs
      {health,discovery,collections,collection_config,documents,search,files,chunks,pages,jobs,monitoring}.py
    tools/                       # MCP layer — 36 @mcp.tool wrappers (1 line each) over the SDK
      __init__.py                #   register_all(mcp, sdk)
      <same 11 domain modules>
  tests/unit/{test_sdk,test_auth,test_tool_registration}.py
services/docforge_mcp/.env       # MCP_TRANSPORT/HOST/PORT/HTTP_PATH/AUTH_TOKEN + DOCFORGE_API_URL
docker-compose.yml               # `mcp` service (docforge-mcp:latest, 10030:9000, depends_on docforge)
docker-compose.dev.yml           # mcp volume mount + DEBUG
.mcp.json                        # local stdio entry repointed to src/docforge_mcp/entrypoint.py
```

### Key decisions — P8
- **Pure HTTP client**: SDK calls `POST/GET /api/v1/...`, never imports `libs/` domain → MCP stays out of the layer DAG.
- **Dedicated minimal image** (not shared docforge:latest): ~150 MB, independent deploy, smaller attack surface for the exposed component.
- **Self-contained `McpConfig`** (not RUNTIME_CONFIG): avoids forcing Postgres/S3 secrets on a client; keeps standalone stdio working.
- **Package named `mcp_app`-style under `libs/`, never `mcp/`** — a top-level `mcp` package would shadow the third-party `mcp` lib.
- **Two-layer split**: `sdk/` (knows the API: paths/bodies, typed, testable) vs `tools/` (presents to the LLM: docstrings/schemas). Tools are 1-line wrappers.
- **Bi-transport**: `stdio` (local Claude Desktop, logs to STDERR — stdout is the protocol channel) | `streamable-http` (container, `stateless_http=True`+`json_response=True`).
- **Bearer auth** via custom Starlette middleware (built-in FastMCP auth is OAuth2/overkill); HTTP mode refuses to boot without `MCP_AUTH_TOKEN`.
- **36 tools** = health(1)+discovery(1)+collections(3)+config(5)+documents(6)+search(2)+files(4)+chunks(3)+pages(4)+jobs(3)+monitoring(4). Search exposes filters/weights/debug; page screenshot returns an MCP `Image`.
- Windows gotcha: log messages must stay ASCII (cp1252 console can't encode `→`); use `->`.
