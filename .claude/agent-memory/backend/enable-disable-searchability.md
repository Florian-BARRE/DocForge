---
name: enable-disable-searchability
description: How reversible chunk/document enable-disable works — search filter injection point, the toggle facade, is_indexed as the "has Qdrant point" signal, and the deferred re-embed
metadata:
  type: project
---

The reversible enable/disable (searchability) feature — a toggle is a FLAG flip, never a re-embed.
All paths in `src/docforge-rework/`.

**Why:** users must be able to hide/show chunks and documents from search at any time without losing
ingestion work (no re-parse/re-embed). Vecteur-maigre: `enabled` is a lean filterable bool payload.

**How to apply:**
- Effective chunk enabled = `enabled_override ?? role_default_enabled(role)`. `role_default_enabled`
  (`shared/libs/public_models/chunk_role.py`) is THE single policy — never inline the rule. Chunk
  table columns (P2): `documents.enabled`, `chunks.role`, `chunks.enabled_override` (bool NULLABLE).
- **Search exclusion is injected in `SearchFacade.hybrid` (facades/search_facade.py), NOT the router** —
  so it is unbypassable. It always adds `Match(field="enabled", value=True)` and, for disabled
  documents, a `must_not` (`exclusions=[MatchAny("document_id", <disabled ids>)]`) fed by a bounded PG
  lookup `DocumentApi.list_disabled_ids(collection_id)`. Chose this over a per-point `doc_enabled`
  payload: a doc-disable stays ONE cheap PG flag with zero Qdrant fan-out.
- `QdrantSearchApi.hybrid` gained an `exclusions` kwarg → `models.Filter(must=…, must_not=…)`.
- **Toggle facade = `EnablementFacade` (`db.enablement`)**, wired in database.py. `set_document_enabled`
  is PG-only. `set_chunks_enabled(chunk_ids, enabled)` sets `enabled_override`, recomputes effective,
  and flips the point payload via `QdrantIndexApi.set_payload` (vector untouched). set_payload runs
  INSIDE the PG session block so a Qdrant failure rolls the override back.
- **`chunk.is_indexed` is the "has a Qdrant point" signal** — no Qdrant existence query needed.
  Enabling a chunk with `is_indexed=False` (a never-embedded header/footer/toc/boilerplate) returns
  `reindex_required=True` and fabricates NO point (no false "searchable" claim). The on-demand
  re-embed pipeline is deferred to a later phase; the override is still persisted so it can run later.
- **Routes**: `PATCH /documents/{id}/enabled` (documents router); `PATCH /chunks/{id}/enabled` +
  bulk `PATCH /chunks/enabled` (explorer router — where chunks are read). Bulk reports unknown ids in
  `not_found` instead of erroring; single 404s. Facade returns `ChunkToggle` payloads. See
  [[hybrid-search-endpoint]] for the surrounding search path.
- **Not yet done (flag for follow-up)**: a BOOL payload index on `enabled` in `QdrantCollectionApi.ensure`
  (filter is correct without it, just unindexed); the on-demand re-embed that consumes `reindex_required`.
</content>
