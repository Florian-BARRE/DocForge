---
name: metadata-search-paths
description: Where each metadata search vector/payload is written and read — the four-way write split and the read validation seam
metadata:
  type: project
---

# Metadata search — write/read path split (V1)

The metadata-search feature spreads its WRITE across four disjoint producers, keyed by (scope × surface):

- **Chunk-scope SEMANTIC** → written by the ingest **embed node** (`nodes/embed/base/node.py::__embed_semantic_fields`, dense only) into `meta_<slug>_dense` on content points, via the translator's `item.fields`.
- **Chunk-scope FILTERABLE** → written by the **translator** (`worker/.../persistence/translator.py`, `__translate_chunks`) into the point payload (`source.generated_meta` ∩ filterable).
- **Doc-scope FILTERABLE** → written by the best-effort **FilterSyncFacade** hook after `index()` (payload set_payload).
- **Doc-scope SEMANTIC + LEXICAL** → written by the best-effort **MetaVectorSyncFacade** hook (`update_vectors` into `meta_<slug>_dense` / `meta_<slug>_bm25`). Doc-scope only (`DocumentApi.get_searchable_metadata` filters `scope==DOCUMENT`).

**Known gap:** there is NO producer for **chunk-scope LEXICAL**. The embed node does dense only for chunk fields; MetaVectorSync is doc-scope only. Yet a generated chunk field may be flagged `lexical=True` (collections router allows it), so the collection declares `meta_<slug>_bm25` but nothing ever populates it.

**READ side:** vector-name resolution lives ONLY in `app/.../search/target_resolver.py::TargetVectorResolver`. Target validation is done **router-side** against the DB schema (`routers/search/helpers.py::validate_search_targets`), NOT graph-side. `SearchContract.{filterable,semantic,lexical}_fields` + `collection_id` are built but **never read** by any node (only `embed_kind`/`embed_config` are consumed by the encode node) — their docstrings claiming a query-intake node "drops/rejects" against them describe behaviour that does not exist.

**Why:** captured during the V1 read-only quality-gate audit. **How to apply:** when debugging "metadata search returns nothing", check which of the four producers owns that (scope × surface) cell; a chunk-scope lexical field is a silent dead end by construction. When reasoning about contract validation, remember it is router-side, not in the graph.
