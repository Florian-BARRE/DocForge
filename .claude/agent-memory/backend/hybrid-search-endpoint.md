---
name: hybrid-search-endpoint
description: The POST /api/v1/collections/{id}/search router — now DELEGATES to CONTEXT.search_service (graph pipeline); router is a thin 404/409/422 gate + ColBERT-degradation diagnostic + Hit mapper
metadata:
  type: project
---

`POST /api/v1/collections/{collection_id}/search` (`app/backend/routers/search/`) turns a query
string into ranked hydrated chunk hits. Body `{query, limit=10, filters?, use_late_interaction?,
rescore_pool_size?}`.

**⚠️ CUT OVER TO THE GRAPH (2026-07-15):** the router NO LONGER hand-rolls retrieval. It DELEGATES to
`CONTEXT.search_service.search(collection_id, query, top_k=, filters=, use_late_interaction=,
rescore_pool_size=)` → `SearchResult`. The graph (SearchPipeline default blob) now embeds the query
(its own `encode` node reuses the collection embedder) and runs hybrid fusion + hydration. The router
is a THIN gate + diagnostic layer only. It no longer calls `CONTEXT.database.search.hybrid`,
`QueryEmbedder.embed()`/`.embed_colbert()`, or `VectorNames`/`SparseVec` (those imports were removed).

**What the router STILL owns (parity-critical, in order):**
- 404 when `collections.get` is None.
- 409 when `SearchHelpers.embed_node_blob(collection.pipeline)` is None (blob still located here — for
  the 409 AND the ColBERT-capability check).
- Resolve `use_late_interaction` + `rescore_pool_size` request-over-`collection.search`-config (request
  wins; else config; else off / 100). These are forwarded to the service, not used locally.
- ColBERT degradation note: if `use_late_interaction` on but `QueryEmbedder(embed_blob).wants_colbert()`
  is False → `debug_info={"late_interaction_skipped":"collection has no colbert vectors — re-ingest
  with embed_colbert"}` + log line; else None. `QueryEmbedder` is kept ONLY for this capability check
  (its `.embed()`/`.embed_colbert()` are dead in the router — the graph's `encode` node embeds now, and
  degrades gracefully itself: it only embeds colbert when the flag is on AND `embedder._wants_colbert()`).
- 422 filterability gate: `SearchHelpers.build_conditions(request.filters, schema)` — raise 422 on
  `invalid` BEFORE the service call (the graph trusts the filters; only `invalid` is used, conditions
  discarded). Blank/whitespace query → 422 via `SearchRequest` field_validator.
- Map `SearchResult.hits` (public_models `Hit`) → `SearchHitModel` via `SearchHelpers.to_hit_model(hit)`:
  `chunk_id/document_id/score/text` off the Hit, `chunk_index`/`token_count` lifted from `Hit.metadata`
  (the read port hydrates them there). The old `to_hit(SearchHit)` mapper was removed.
- `rescore_pool_size` override: `SearchService.search` accepts it and, when not None, injects it into the
  retrieve node's config (`RetrieveHybridConfig.rescore_pool_size`) on the default blob BEFORE build
  (`__inject_rescore_pool_size` finds the `id="retrieve"` ActionNodeBlob and sets `config[...]`). The
  router always passes a concrete int (default 100), so the injection always fires → parity with the old
  facade default. Un-ingested-collection empty-result guard now lives inside the graph's read port /
  SearchFacade, not the router.

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
