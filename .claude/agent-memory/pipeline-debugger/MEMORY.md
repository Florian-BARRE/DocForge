---
name: pipeline-debugger-memory
description: Known failure patterns, service endpoints, and diagnostic notes for the DocForge S0→S6 pipeline
metadata:
  type: project
---

# Pipeline Debugger Memory

## Known failure patterns

| Symptom | Root cause | Fix |
|---|---|---|
| S6 skips Qdrant | `collection_id=None` in `arq_pool.enqueue_job()` | `documents/router.py` — pass `collection_id=str(collection_id)` |
| Chunk count = 0 | `S4_ENABLED=false` | Set `S4_ENABLED=true` in `services/docforge/.env` |
| S2 silently skips all figures | `S2_ENRICH_ENABLED=false` | Set `S2_ENRICH_ENABLED=true` |
| TEI unreachable | Wrong `TEI_BASE_URL` or container down | Check `services/docforge/.env` + `docker compose ps` |
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
| TEI | http://localhost:8080 | GET /health |
| Redis | redis://localhost:6379 | `redis-cli ping` |
| PostgreSQL | localhost:5432 | `pg_isready` |

## Key env flags

| Flag | Default | Controls |
|---|---|---|
| `S2_ENRICH_ENABLED` | false | S2 OCR/VLM enrichment |
| `S4_ENABLED` | false | S4 structure-aware chunking |
| `S6_ENABLED` | false | S6 BGE-M3 embed + Qdrant indexing |
| `ENRICH_MAX_BUDGET_USD` | 0.0 | Budget cap (0 = unlimited) |
| `TEI_BASE_URL` | http://tei:80 | TEI embed service URL |
| `QDRANT_HOST` | qdrant | Qdrant hostname |

## Stage file map

| Stage | File |
|---|---|
| S0 | `src/docforge/libs/pipeline/stages/s0_ingest.py` |
| S1 | `src/docforge/libs/pipeline/stages/s1_parse.py` |
| S2 | `src/docforge/libs/pipeline/stages/s2_enrich.py` |
| S4 | `src/docforge/libs/pipeline/stages/s4_chunk.py` |
| S5 | `src/docforge/libs/pipeline/stages/s5_contextualize.py` |
| S6 | `src/docforge/libs/pipeline/stages/s6_embed_index.py` |
| Engine | `src/docforge/libs/pipeline/engine.py` |
