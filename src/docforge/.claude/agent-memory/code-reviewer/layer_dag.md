---
name: layer-dag
description: DocForge libs layer DAG — concrete import rules to enforce on review, esp. storage vs search
metadata:
  type: constraint
---

DocForge `libs/` layer DAG (from CLAUDE.md): `domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`. A layer never imports a layer above it.

**Concrete rules verified on review (enforce these):**

- `libs/storage/qdrant/*` may import `libs.search.field_index` (the shared low-level fusion/tuning module — `RetrievalTuning`, `FieldIndexHelpers`, `CONTENT_DENSE/SPARSE`) but must NEVER import `libs.search.hybrid` or `libs.search.pipeline`. `field_index/` itself imports nothing from hybrid/pipeline. This is WHY `RetrievalTuning` lives in `field_index`, not `hybrid` — storage consumes it.
- `libs/search/pipeline/` (engine) may import `libs.search.hybrid` and `libs.providers.*` and `libs.config.*`.
- `libs/pipeline/assembly/registry.py` (`build_search_pipeline`) uses LAZY imports for `libs.search.pipeline.SearchPipelineEngine` to honour pipeline(3)→search(2) without a module-level cycle. `search_config.py` (config layer) also lazy-imports provider configs inside model_validators to stay a leaf.

**How to apply:** on any storage/search/pipeline review, grep for upward imports: `grep -rn "search.hybrid\|search.pipeline" libs/storage/` must be empty. Provider/engine config classes in `libs/config/` must not import concrete providers at module level.
