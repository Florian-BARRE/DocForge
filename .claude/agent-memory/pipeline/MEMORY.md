---
name: pipeline-memory
description: Pipeline architecture + runtime failure patterns, service endpoints, env flags, stage file map
metadata:
  type: project
---

# Pipeline — Memory Index

## Known failure patterns

| Symptom | Root cause | Fix |
|---|---|---|
| Reingest "original not found" → doc stuck `pending` | S0 download in `engine.run` step 2 is OUTSIDE the fail-closed guards; OR the repro races a collection-delete / polls stale chunks | Wrap step-2 download → `mark_failed`+raise; verify reingest by polling REAL status, not `wait_done`. See [[reingest-failclosed-and-corpus-phrases]] |
| "Search misses a doc by its own phrase" | corpus `searchable_phrase` shared across all formats of a (type,lang) pair → not distinctive | raise `top_k` (>=~20-30) or scope to one doc. See [[reingest-failclosed-and-corpus-phrases]] |
| S6 skips Qdrant | `collection_id=None` in `arq_pool.enqueue_job()` | `documents/router.py` — pass `collection_id=str(collection_id)` |
| Chunk count = 0 | `S4_ENABLED=false` | Set `S4_ENABLED=true` in `services/docforge/.env` |
| S2 silently skips all figures | `S2_ENRICH_ENABLED=false` | Set `S2_ENRICH_ENABLED=true` |
| bge unreachable | Wrong `TEI_BASE_URL` or `bge_server` container down | Check `services/docforge/.env` + `docker compose ps bge` + `docker compose logs bge` (first boot is slow — downloads BGE-M3 + reranker from HF) |
| Qdrant collection missing | `ensure_collection()` failed | Check `QDRANT_HOST`/`QDRANT_PORT` connectivity |
| SeaweedFS 403 on upload | Bucket not initialized | Call `POST /api/v1/collections` to provision the bucket |
| Docling parse returns empty IR | Corrupted PDF or Gotenberg timeout | Check Gotenberg logs: `docker compose logs gotenberg` |
| arq job stuck in `running` | Worker crashed during stage | Check `docker compose logs worker --tail=100` |

## Service endpoints (dev)

| Service | URL | Health check |
|---|---|---|
| API | http://localhost:8000 | GET /api/v1/health |
| API docs | http://localhost:8000/docs | browser |
| Gotenberg | http://localhost:3000 | GET /health |
| SeaweedFS | http://localhost:8333 | GET /status |
| SeaweedFS Filer | http://localhost:8888 | GET / |
| Qdrant | http://localhost:6333 | GET /healthz |
| bge_server | http://localhost:10026 | GET /health |
| Redis | redis://localhost:6379 | `redis-cli ping` |
| PostgreSQL | localhost:5432 | `pg_isready` |

## Key env flags

| Flag | Default | Controls |
|---|---|---|
| `S2_ENRICH_ENABLED` | false | S2 OCR/VLM enrichment |
| `S4_ENABLED` | false | S4 structure-aware chunking |
| `S6_ENABLED` | false | S6 BGE-M3 embed + Qdrant indexing |
| `ENRICH_MAX_BUDGET_USD` | 0.0 | Budget cap (0 = unlimited) |
| `TEI_BASE_URL` | http://bge_server:80 | bge embed service URL (stopgap; provider URLs migrating to per-collection DB config) |
| `BGE_RERANKER_URL` | http://bge_server:80 | bge rerank service URL |
| `QDRANT_HOST` | qdrant | Qdrant hostname |

## Stage file map

| Stage | File |
|---|---|
| S0 | `src/docforge/common/common_libs/pipeline/stages/s0_ingest/core.py` |
| S1 | `src/docforge/common/common_libs/pipeline/stages/s1_parse/core.py` |
| S2 | `src/docforge/common/common_libs/pipeline/stages/s2_enrich/core.py` |
| S4 | `src/docforge/common/common_libs/pipeline/stages/s4_chunk/core.py` |
| S5 | `src/docforge/common/common_libs/pipeline/stages/s5_contextualize/core.py` |
| S6 | `src/docforge/common/common_libs/pipeline/stages/s6_embed_index/core.py` |
| Engine | `src/docforge/worker/libs/pipeline/engine.py` |
