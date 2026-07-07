---
name: rework-search-endpoint
description: Rework hybrid-search read path (app/backend/routers/search/) — correctness seams and the never-ingested 500 gap
metadata:
  type: feedback
---

The rework search endpoint is `POST /api/v1/collections/{collection_id}/search`
(`app/backend/routers/search/`: router + models + embedder + helpers). Reviewed 2026-07-07.

**How it must stay correct (verify on any change here):**
- Query is embedded with the collection's OWN embed node, rebuilt from the stored blob via
  `NodeRegistry.get(EMBED_FAMILY, blob.kind)` + re-validated `Config` (extra="forbid" → drift fails
  loud). `QueryEmbedder` drives the node's protected `_embed_dense` / `_embed_sparse` hooks on a
  1-element batch instead of the heavy `run()`. Provider stays interchangeable.
- Query vector dicts MUST be keyed by `VectorNames.CONTENT_DENSE` / `VectorNames.CONTENT_SPARSE`
  (= "content_bm25"), the SAME constants the persistence side writes — never string literals.
- openai_compatible degrades to dense-only gracefully: base `_embed_sparse` returns None, and
  `QueryEmbedder.__maybe_sparse` returns None on that → sparse dict is None, no crash. Matches how
  ingestion drops the sparse axis for the same provider. Do not break this symmetry.
- api_key lives on the embed config; it must never be logged (only `kind` + `embed_sparse` are) nor
  echoed in the response. Response is the flat SearchHit view only (chunk_id/document_id/score/text/…).

**Durable gap found (should-fix):** neither the router nor `SearchFacade.hybrid` nor
`QdrantSearchApi.hybrid` guards `collection_exists`. The Qdrant collection is created LAZILY at first
indexing (`collections_facade.create` does NOT provision it), so searching a collection that was
created but never ingested calls `client.query_points` on a missing collection → qdrant raises →
`@auto_handle_errors` wraps it as HTTP 500 (with traceback in the detail). Fix belongs in the facade
seam: guard `collection_exists` → return `[]`. This is the reusable "no vectors yet" robustness case.

**Note:** the whole rework app has ZERO auth wired (no `require_collection_role`/`require_capability`
anywhere in `app/backend/routers/`) — the auth memories describe the FROZEN legacy tree, not rework.
So "missing auth on search" is consistent with the tree, not a regression; flag it as a product gap,
not a defect of a single PR.
