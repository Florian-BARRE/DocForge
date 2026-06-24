---
name: layer-dag
description: DocForge libs layer DAG — concrete import rules to enforce on review, esp. storage vs search
metadata:
  type: constraint
---

DocForge layer DAG (from CLAUDE.md): `domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`. A layer never imports a layer above it. The shared buckets live under `common_libs/<bucket>` (imported `from common_libs.<bucket> import …`); the app-only search modules `search.hybrid`/`search.pipeline` live under `backend.libs.search` (imported `from backend.libs.search.* import …`), while `search.field_index` stays shared in `common_libs`.

**Concrete rules verified on review (enforce these):**

- `common_libs/storage/qdrant/*` may import `common_libs.search.field_index` (the shared low-level fusion/tuning module — `RetrievalTuning`, `FieldIndexHelpers`, `CONTENT_DENSE/SPARSE`) but must NEVER import `backend.libs.search.hybrid` or `backend.libs.search.pipeline`. `field_index/` itself imports nothing from hybrid/pipeline. This is WHY `RetrievalTuning` lives in `common_libs/search/field_index`, not `hybrid` — storage (shared) consumes it, and storage cannot depend on app-only code.
- `backend.libs.search.pipeline` (engine) may import `backend.libs.search.hybrid` and `common_libs.providers.*` and `common_libs.config.*`.
- `build_search_pipeline` lives in `app/backend/libs/search/builder.py` (`from backend.libs.search.builder import build_search_pipeline`) — it is NO LONGER a method on `common_libs/pipeline/assembly/registry.py`. It uses LAZY imports for `backend.libs.search.pipeline.SearchPipelineEngine` to honour pipeline(3)→search(2) without a module-level cycle. `search_config.py` (config layer) also lazy-imports provider configs inside model_validators to stay a leaf.

**How to apply:** on any storage/search/pipeline review, grep for upward imports: `grep -rn "backend.libs.search.hybrid\|backend.libs.search.pipeline" src/docforge/common/common_libs/storage/` must be empty (shared storage must never reach into app-only search). Provider/engine config classes in `common_libs/config/` must not import concrete providers at module level.
