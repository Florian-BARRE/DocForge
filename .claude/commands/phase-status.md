---
name: phase-status
description: Show DocForge current phase implementation status (what is done vs pending)
user-invocable: true
allowed-tools: "Read(*), Bash(*)"
---

# Phase Status

Report what is implemented and what is pending across all 6 DocForge phases.

## Steps

1. **Check current phase** from CLAUDE.md phase table.

2. **P1 — Foundation** — check existence and non-emptiness of:
   - [ ] `src/docforge/common/common_libs/ir/models.py`
   - [ ] `src/docforge/common/common_libs/storage/postgres/`
   - [ ] `src/docforge/common/common_libs/storage/s3/client.py`
   - [ ] `src/docforge/common/common_libs/providers/converter/gotenberg.py`
   - [ ] `src/docforge/common/common_libs/providers/parser/docling_backend.py`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s0_ingest.py`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s1_parse.py`
   - [ ] `src/docforge/app/backend/routers/documents/router.py`
   - [ ] `docker-compose.yml`

3. **P2 — Stage Engine** — check:
   - [ ] `src/docforge/common/common_libs/pipeline/fingerprint.py`
   - [ ] `src/docforge/common/common_libs/pipeline/node_cache.py`
   - [ ] `src/docforge/common/common_libs/pipeline/provider_cache.py`
   - [ ] `src/docforge/common/common_libs/pipeline/engine.py`
   - [ ] `src/docforge/common/common_libs/pipeline/tasks.py`
   - [ ] `src/docforge/common/common_libs/pipeline/worker.py`
   - [ ] `src/docforge/common/common_libs/storage/postgres/repositories/job_repo.py`
   - [ ] `src/docforge/app/backend/routers/jobs/router.py`
   - [ ] `src/docforge/app/backend/routers/playground/router.py`
   - [ ] `migrations/versions/002_gin_indexes.py`

4. **P3 — Enrichment** — check:
   - [ ] `src/docforge/common/common_libs/providers/chain.py`
   - [ ] `src/docforge/common/common_libs/providers/classifier/`
   - [ ] `src/docforge/common/common_libs/providers/ocr/`
   - [ ] `src/docforge/common/common_libs/providers/vlm/`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s2_enrich.py`

5. **P4 — Retrieval** — check:
   - [ ] `src/docforge/common/common_libs/ir/chunk.py`
   - [ ] `src/docforge/common/common_libs/providers/embed/tei.py`
   - [ ] `src/docforge/common/common_libs/storage/qdrant/client.py`
   - [ ] `src/docforge/common/common_libs/storage/postgres/repositories/chunk_repo.py`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s4_chunk.py`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s5_contextualize.py`
   - [ ] `src/docforge/common/common_libs/pipeline/stages/s6_embed_index.py`
   - [ ] `migrations/versions/003_chunks.py`

6. **P5 — Collections API** — check:
   - [ ] `src/docforge/common/common_libs/retrieval/hybrid_search.py`
   - [ ] `src/docforge/app/backend/routers/chunks/router.py`
   - [ ] Collection endpoints: GET schema, PUT pipeline, POST reindex, POST search (check router.py)
   - [ ] Document endpoints: GET markdown (check documents/router.py)
   - [ ] `collection_id` passed in `arq_pool.enqueue_job()` call in documents/router.py

7. **P6 — UI + MCP** — check:
   - [ ] `src/docforge/app/frontend/` (React app)
   - [ ] MCP server module

8. **Output a clean table** with ✅/⏳/❌ per phase and key files.
