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
   - [ ] `src/docforge/libs/ir/models.py`
   - [ ] `src/docforge/libs/storage/postgres/`
   - [ ] `src/docforge/libs/storage/s3/client.py`
   - [ ] `src/docforge/libs/providers/converter/gotenberg.py`
   - [ ] `src/docforge/libs/providers/parser/docling_backend.py`
   - [ ] `src/docforge/libs/pipeline/stages/s0_ingest.py`
   - [ ] `src/docforge/libs/pipeline/stages/s1_parse.py`
   - [ ] `src/docforge/backend/routers/documents/router.py`
   - [ ] `docker-compose.yml`

3. **P2 — Stage Engine** — check:
   - [ ] `src/docforge/libs/pipeline/fingerprint.py`
   - [ ] `src/docforge/libs/pipeline/node_cache.py`
   - [ ] `src/docforge/libs/pipeline/provider_cache.py`
   - [ ] `src/docforge/libs/pipeline/engine.py`
   - [ ] `src/docforge/libs/pipeline/tasks.py`
   - [ ] `src/docforge/libs/pipeline/worker.py`
   - [ ] `src/docforge/libs/storage/postgres/repositories/job_repo.py`
   - [ ] `src/docforge/backend/routers/jobs/router.py`
   - [ ] `src/docforge/backend/routers/playground/router.py`
   - [ ] `migrations/versions/002_gin_indexes.py`

4. **P3 — Enrichment** — check:
   - [ ] `src/docforge/libs/providers/chain.py`
   - [ ] `src/docforge/libs/providers/classifier/`
   - [ ] `src/docforge/libs/providers/ocr/`
   - [ ] `src/docforge/libs/providers/vlm/`
   - [ ] `src/docforge/libs/pipeline/stages/s2_enrich.py`

5. **P4 — Retrieval** — check:
   - [ ] `src/docforge/libs/ir/chunk.py`
   - [ ] `src/docforge/libs/providers/embed/tei.py`
   - [ ] `src/docforge/libs/storage/qdrant/client.py`
   - [ ] `src/docforge/libs/storage/postgres/repositories/chunk_repo.py`
   - [ ] `src/docforge/libs/pipeline/stages/s4_chunk.py`
   - [ ] `src/docforge/libs/pipeline/stages/s5_contextualize.py`
   - [ ] `src/docforge/libs/pipeline/stages/s6_embed_index.py`
   - [ ] `migrations/versions/003_chunks.py`

6. **P5 — Collections API** — check:
   - [ ] `src/docforge/libs/retrieval/hybrid_search.py`
   - [ ] `src/docforge/backend/routers/chunks/router.py`
   - [ ] Collection endpoints: GET schema, PUT pipeline, POST reindex, POST search (check router.py)
   - [ ] Document endpoints: GET markdown (check documents/router.py)
   - [ ] `collection_id` passed in `arq_pool.enqueue_job()` call in documents/router.py

7. **P6 — UI + MCP** — check:
   - [ ] `src/docforge/frontend/` (React app)
   - [ ] MCP server module

8. **Output a clean table** with ✅/⏳/❌ per phase and key files.
