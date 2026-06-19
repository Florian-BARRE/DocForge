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

> **⚠️ Structure refactor (2026-06-19):** `libs/` was reorganized **by concept**. The paths
> in the per-phase sections below use the OLD flat names — translate them with this map:
>
> | Old path | New path |
> |---|---|
> | `libs/ir/` | `libs/core/ir/` |
> | `libs/metadata/` (schema) | `libs/core/metadata/` |
> | `libs/pipeline/pipeline_config.py` | `libs/core/contracts/pipeline_config/` (package) |
> | `libs/providers/` | `libs/capabilities/` |
> | `libs/providers/registry.py` | `libs/engine/assembly/registry.py` |
> | `libs/storage/` | `libs/data/storage/` |
> | `libs/retrieval/`, `libs/metadata/indexer.py` | `libs/data/retrieval/` |
> | `libs/pipeline/` | `libs/engine/` (engine.py → `engine/orchestrator/`) |
> | `libs/admission/`, `libs/config_validation/` | `libs/governance/` |
>
> Several large files became packages (`engine/orchestrator/`, `s4_chunk/`, `s2_enrich/`,
> `contracts/pipeline_config/`). Imports are `from libs.<bucket>...`. See CLAUDE.md for the layer DAG.

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
