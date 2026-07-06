---
name: docforge-rework-explorer-api
description: docforge-rework document-explorer read API — router wiring, facade seams, and two non-obvious env/introspection gotchas
metadata:
  type: project
---

The document-explorer READ API in the parallel rewrite at `src/docforge-rework/` (separate tree from
`src/docforge/`; storage layer is `shared/libs/services/db/` with `Database` façade aggregate exposing
`db.collections/documents/ingestion/jobs/...`, imported as `from shared_libs.services.db import ...`).

**Why:** built the explorer (browse everything behind a collection) as `app/backend/routers/explorer/`
(no router prefix → owns both `/collections/{id}/documents` and `/documents/{id}/{pages,ir,chunks}` +
DELETE, with explicit full paths) and `routers/blobs/` (prefix `/blobs`, streams `Response(content=bytes,
media_type=blob.mime_type)` — the ONE route with no Pydantic response_model, `response_class=Response`).
Admission (`POST /documents`) stays in the separate `documents` router; explorer is pure read + the
document delete. `DocumentsFacade` already had everything; I added bulk read seams to avoid a 89-chunk
N+1: `ChunkApi.get_composition_for_document` / `get_metadata_for_document` + facade wrappers
`get_document_chunk_composition` / `get_document_chunk_metadata`. Metadata rows carry `field_id` only —
resolve names via `db.collections.get_schema(collection_id)` → `{row.id: row.field_name}`; use the VALUE
row's `origin` (not the field's declared origin). `DocumentsFacade.delete()` already does the coherent
cross-store purge (Qdrant → PG cascade → orphan-only blob purge, shared blobs survive) — use it for 204/404.

**How to apply:** two gotchas that cost real time here —
1. **Route introspection**: the rework app wraps included routers in a custom `_IncludedRouter`, so
   `app.routes` is NOT flattened (top level shows only the wrappers + built-ins, ~12 entries). A
   route-registration unit test MUST assert against `app.openapi()["paths"]`, never `app.routes`. Store-
   backed route tests live in `tests/live`; `tests/units/api` boots the real app with LAZY store connects
   (`conftest.py` `client` fixture) so only no-store checks work there (path-param UUID → 422 before the
   handler; openapi registration). Bad `content_hash` on `/blobs` is `str`-typed → no 422, hits the DB.
2. **S3 blob route 500s in the running rework stack**: `docker-compose.rework.yml` sets
   `S3_ENDPOINT_URL=http://rework_seaweedfs:8333` — botocore REJECTS the underscore in the host
   (`ValueError: Invalid endpoint`) before connecting, so EVERY S3 read/write 500s app-wide (not just the
   blob route). The blobs are fine (written under an earlier valid config); the valid alias
   `docforge-rework-seaweedfs` (no underscore, same box) proves the path. Infra-owned fix (rename the
   compose service/alias or set a valid host). See [[provider-config-per-collection]].
