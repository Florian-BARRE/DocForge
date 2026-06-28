---
name: api-surface-map
description: Authoritative shape of the /api/v1 REST surface — 12 routers, 38 routes, prefix algebra, the 2 SSE routes, the 1 bytes route, and the files-return-URL-not-bytes distinction
metadata:
  type: project
---

The full `/api/v1` REST surface, the source of truth the standalone MCP server (`src/mcp/`, 36 tools)
mirrors 1:1.

**Why:** repeatedly asked to keep MCP/clients compatible with the whole API; the prefix algebra and
the streaming/binary edge cases are easy to get wrong from the router files alone.
**How to apply:** when adding/renaming a route, update the MCP SDK + this note; respect the gotchas below.

## Prefix algebra (defined ONCE in `app.py:66-81`, leaf paths in routers are relative)
- `V1=/api/v1`; `COL=/api/v1/collections`; `DOC=COL/{collection_id}/documents`.
- `files`/`chunks`/`pages` mount under `DOC/{document_id}[/chunks|/pages]`; `search` mounts at `DOC`
  (its one per-doc route uses a `/{document_id}/search` leaf). `jobs`+`monitoring` are global under `V1`.
- Empty-string leaf paths (`""`) → exact URL with no trailing segment: `limits` GET/PUT (`…/limits`),
  `jobs` list (`/api/v1/jobs`), discovery (`/api/v1/discovery`).

## Count: 38 routes total = 36 synchronous (MCP-eligible) + 2 SSE.

## SECTION B — SSE routes (NOT wrappable as a synchronous MCP tool; no response_model)
Both return `sse_starlette.EventSourceResponse`. Companion REST snapshot exists for each:
- `GET …/documents/stream` (`documents/router.py:192`) — collection-scoped job.updated+stage.progress;
  snapshot = `…/documents/list` + `…/{document_id}`. MUST be declared BEFORE `/{document_id}` (FastAPI
  matches in declaration order, else "stream" is captured as a doc id).
- `GET /api/v1/monitoring/stream` (`monitoring/router.py:108`) — all events; snapshot = `…/overview`.

## SECTION A — bytes route (raw, no response_model)
- `GET …/pages/{page_number}/screenshot` (`pages/router.py:96`) → `Response` `image/png` raw PNG bytes
  (PyMuPDF render in a thread pool). The MCP page tool returns this as an `Image`.

## files/* return a URL, NOT bytes
`…/{document_id}/{original|markdown|pdf|figures/{block_id}}` (`files/router.py`) return JSON
`PresignedUrlResponse{url,expires_in}` — a pre-signed S3 URL. Delivering file *content* is a 2-step
fetch (follow the URL, unauthenticated S3 GET). `figures/{block_id:path}` allows slashes in block_id.

## Non-200 codes to model
- 201 `POST /collections/create`; 202 `…/ingest` + `…/reingest`.
- Ingest ladder (`documents/router.py:39`): 400 empty → 404 no collection → 422 bad metadata JSON →
  415/413/422 admissibility → dedup short-circuit → 429 capacity / 409 budget (Brique D, after dedup).
- files/screenshot: 404 missing / 409 doc not `done`.
- search: 503 provider unbuildable/unreachable; 200 + `note` + empty results when retrieval disabled.

## UI data fields (additive, 2026-06-28)
- `collections/list` items carry `document_count` + `processed_count` (status='done'), merged from
  `DocumentRepository.counts_by_collection(session)` — ONE grouped COUNT (+`func.count().filter(...)`),
  no N+1. Defaults 0 so a collection absent from the tally map stays valid (model_copy override).
- `DocumentResponse.pipeline_duration_ms: int | None` = latest done job's (finished_at-started_at) in ms.
  List path: `JobRepository.latest_done_durations_by_collection(session, col_id)` (Postgres DISTINCT ON
  (document_id) ordered created_at desc, one query/page). Detail path: `_latest_done_duration_ms(jobs)`
  helper computes from the already-loaded jobs (no extra query). None when no timed done job.
- MagicMock `__int__`→1, so `model_validate(mock)` coerces unset int fields then `model_copy(update=)`
  overrides — but new repo mocks MUST set return defaults (`counts_by_collection`→{},
  `latest_done_durations_by_collection`→{}) or model_copy injects a Mock that breaks JSON serialization.

## Recently added (post-7-tool MCP) — Briques A/C/D
- A: `/api/v1/jobs` (list/`{id}`/`{id}/cancel`) + `/api/v1/monitoring/{queue,workers,overview,discovery}`.
- C: the 2 SSE routes above.
- D: `…/limits` GET+PUT + `/api/v1/monitoring/resources`; ingest gained 429/409.
