---
name: colbert-named-vector
description: The ColBERT third named vector end-to-end — persistence (content_colbert multivector, content-point-only) AND search-side late-interaction re-score + reindex semantics
metadata:
  type: project
---

ColBERT is Qdrant named vector `VectorNames.CONTENT_COLBERT = "content_colbert"`, a MAX_SIM
multivector declared by `QdrantVectorSchema.colbert_config(dim)` (int8 scalar quantization +
`on_disk=True` — a ColBERT vector is ~30x a dense one, so it stays off RAM).

**Why:** late-interaction re-scoring needs per-token vectors; naive storage would blow up RAM.

**How to apply (wiring, do not re-derive):**
- Per-chunk ColBERT rides a DEDICATED field `QdrantPoint.multivector: dict[str, list[list[float]]]`
  — never overload the flat `dense` map. `QdrantIndexApi._to_struct` merges it into the same
  named-vector dict handed to qdrant-client.
- The translator (`worker/.../persistence/translator.py` `__translate_chunks`) sets it on the
  CONTENT point only, keyed by `CONTENT_COLBERT`. It must NEVER land on `meta_<slug>_dense`
  metadata vectors nor the metagen post-hoc `update_vectors` path.
- Declaration is gated: `QdrantCollectionApi.ensure(..., colbert_dim=...)` merges
  `colbert_config` into `vectors_config` ONLY when `colbert_dim is not None`, and only on a FRESH
  collection. A named vector cannot be added to an existing Qdrant collection in place →
  **one-way door**: pre-ColBERT collections require drop + re-embed, no in-place migration.
- `colbert_dim` flows: `ChunkEmbeddings.colbert_dim` → `TranslatedRun.colbert_dim` →
  `jobs/core.py` → `IngestionFacade.index(colbert_dim=...)` → `ensure` (plain attribute read).

**Search side (Wave 2 — late interaction re-score):**
- `QdrantSearchApi.hybrid(..., colbert=None, rescore_pool_size=100)`: when `colbert` is given, the
  dense+sparse RRF fusion becomes a NESTED `Prefetch(prefetch=[...branches...],
  query=FusionQuery(RRF), limit=rescore_pool_size)` and the OUTER `query_points` runs
  `query=colbert, using=CONTENT_COLBERT, limit=limit` (MAX_SIM). `colbert=None` is byte-identical
  to the single-stage path. The disabled-doc/enabled filter stays on the INNER branches so a
  re-score can never resurrect a disabled chunk.
- Threaded through `SearchFacade.hybrid` unchanged. `QueryEmbedder` gained `wants_colbert()` (mirrors
  the embedder's config flag — the graceful-guard signal, no Qdrant round-trip) and
  `embed_colbert(query)` (calls the node's `_embed_colbert` on a 1-element batch).
- Router flag resolution: effective `use_late_interaction` = request value, else
  `collection.search.get("use_late_interaction", False)`; pool = `request.rescore_pool_size or
  collection.search.get("rescore_pool_size", 100)`. `collection.search` is an UNTYPED JSONB blob
  (user decision — keys only, no typed SearchConfig).
- GRACEFUL GUARD: flag on but `embedder.wants_colbert()` False (collection never ingested with
  colbert) → degrade to standard hybrid, no 500, and surface `debug_info={"late_interaction_skipped":
  ...}` on `SearchResponse` (new nullable field).

**Reindex semantics (confirmed, no new wiring):**
- Flipping the PIPELINE `embed_colbert` flag changes `collection.pipeline`, whose sha256 is the
  `pipeline_version` (`documents/router.py:_pipeline_version`) — part of the dedup key
  `find_duplicate(collection, source_hash, pipeline_version)`. New hash busts dedup → re-ingest
  re-embeds and populates `content_colbert`. This IS the existing config-version-diff re-embed path.
- The SEARCH flag `use_late_interaction` lives in `collection.search` (NOT hashed into
  pipeline_version) → toggling it needs NO reindex; it only chooses whether to query an existing
  vector.

See [[pipeline-blob-validation]] for the general fail-fast-at-the-edge posture.
