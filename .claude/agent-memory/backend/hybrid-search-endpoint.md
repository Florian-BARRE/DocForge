---
name: hybrid-search-endpoint
description: The POST /api/v1/collections/{id}/search router — how the query is embedded with the collection's own embedder and how vectors are named
metadata:
  type: project
---

`POST /api/v1/collections/{collection_id}/search` (`app/backend/routers/search/`) turns a query
string into ranked hydrated chunk hits. Body `{query, limit=10, filters?}`; delegates the Qdrant
RRF fusion + Postgres hydration to `CONTEXT.database.search.hybrid`.

**Why it exists:** the `SearchFacade.hybrid` took PRE-COMPUTED query vectors and no router exposed it
+ nothing embedded the query. This router closes that gap.

**How to apply / non-obvious wiring:**
- Query embedding REUSES the collection's own embed node (provider-interchangeable). `QueryEmbedder`
  (`embedder.py`) rebuilds the node from the stored blob: `NodeRegistry.get("embed", blob.kind)` →
  `class.Config(**blob.config)` (extra="forbid" re-validates) → instantiate → call the node's
  `_embed_dense([query])` / `_embed_sparse([query])` hooks directly. NOT `run()` — run() needs a whole
  chunk set + contract. Calling the protected hooks is deliberate (engine nodes are the pipeline
  agent's territory — consume, don't modify). No `bind()` needed: the embed hooks use only `self.config`.
- The embed node lives ANYWHERE in the pipeline blob tree — `SearchHelpers.embed_node_blob` walks
  groups (`nodes`) and foreach bodies (`body`) recursively, matching `family == "embed"` (single-use).
- Vector names come from `VectorNames.CONTENT_DENSE` / `.CONTENT_SPARSE` constants (the SAME the
  worker's `RunTranslator` writes) — NEVER string-literal "content_dense"/"content_bm25".
- Sparse is graceful: dense always; sparse dict only when `config.embed_sparse` AND the provider
  returns vectors (openai_compatible has no sparse → dense-only search, no error).
- Filters → Conditions in `SearchHelpers.build_conditions`: scalar → `Match`, list → `MatchAny`, only
  over fields flagged `filterable`; a non-filterable/unknown field → 422 (checked before any search).
- Rejection ladder: 404 unknown collection · 409 no embed node wired · 422 bad filter field
  (also 422 on a blank/whitespace-only query — `SearchRequest` field_validator strips + rejects).
- Un-ingested collection guard lives in `SearchFacade.hybrid` (the reusable seam), NOT the router: a
  collection provisions its Qdrant space lazily at first indexing, so `hybrid` does
  `if not await self._qdrant.raw.collection_exists(name): return []` before `query_points`. Searching a
  created-but-never-ingested collection yields 200 + empty hits, never a 500.
- `SearchHit` (facade payload) carries only `chunk` (Chunk row) + `score`. heading_path and resolved
  metadata are NOT on it — the response exposes chunk-row scalars (id, document_id, text,
  chunk_index, token_count). Adding heading_path/metadata would need a SearchFacade/SearchHit extension.

**Engine is inline-capable (for the graph-based search redesign, 2026-07):** `FlowEngine`
(`shared/libs/pipelines/engine/core.py:47`, `execute` at :435) is a PURE stateless async class — zero
arq/redis/worker imports. `PipelineRunner` (`worker/backend/libs/runner/core.py`) is likewise pure
(imports only `shared_libs.pipelines.*` + `public_models`); it lives under `worker/` but is not
worker-bound. The ONLY arq coupling is `worker/backend/libs/jobs/core.py` (the `ingest_document` task
wrapper). So a search graph CAN be built+validated+run INLINE in the API request (sub-second), via
`FlowEngine.execute(..., timeout_seconds=<short>)` — no worker queue. Ingestion is async-via-arq;
search must be inline. Note: `PipelineRunner`'s output contract is ingestion-specific (`RunBundle`,
runner/core.py:112-118) — search needs its own thin runner / `SearchBundle` contract. All read-side
facade methods retrieval needs are read-only: `collections.get`, `collections.get_schema`,
`search.hybrid`, `ChunkApi.get_by_ids`, `DocumentApi.list_disabled_ids`, `collection_exists`.

**Current app.py wiring reality (supersedes stale notes in [[api-surface-map]]):** each router
self-prefixes and is mounted with `app.include_router(router=..., prefix="/api/v1")`; the search
router uses NO prefix and owns the explicit path `/collections/{collection_id}/search` (explorer
pattern). There are currently NO auth `dependencies=` on any router include.
