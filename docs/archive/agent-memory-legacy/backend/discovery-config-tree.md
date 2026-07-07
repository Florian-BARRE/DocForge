---
name: discovery-config-tree
description: The recursive config_tree describer for /discovery (CHUNK D1) — auto_import path gotcha, field→category glue, ConfigNode shape
metadata:
  type: project
---

# Discovery recursive config_tree (CHUNK D1, built 2026-06-25)

**Why:** the flat `dynamic_fields` surface can't describe non-scalar fields (gates, nested provider
sub-configs, atomic, search retrieve/grouping/mmr) — they were hand-coded in the frontend. The
recursive `config_tree` makes the WHOLE pipeline+search config discovery-driven so the UI renders
generically. ADDITIVE: `dynamic_fields` stays until the frontend cuts over (CHUNK D2).

**How to apply:**
- `ConfigNode`/`ProviderChoice` live in `app/backend/routers/discovery/models.py`. They have MUTUAL
  forward refs (`ConfigNode.choices: list[ProviderChoice]`, `ProviderChoice.params: list[ConfigNode]`)
  → both need `model_rebuild()` after the class block (already there). `ProviderChoice.params` being
  `list[ConfigNode]` (not flat scalars) is THE unlock for nested unions (semantic.embed).
- The describer is `common_libs/pipeline/assembly/config_describer.py` — `describe(model_cls, cfg,
  root_path) -> dict` (plain dicts; the router validates into `ConfigNode`). Static-only
  `ConfigDescriberHelpers`. Walks `model_json_schema()` + `$defs` recursively.
- **auto_import path gotcha (important):** the registry package root is `common_libs.providers.*`.
  The LEGACY `describe.py`/`describe_stages` auto_import list uses `libs.providers.*` which
  `auto_import()` silently swallows (ImportError) — those configs only register as a side effect of
  stage-config lazy validation imports. The recursive describer imports via the path that ACTUALLY
  resolves (`common_libs.providers.*`) and explicitly includes `rerank` + `llm` (describe_stages omits
  them). If you add a category, register it in `_AUTO_IMPORT_PACKAGES` with the `common_libs.` prefix.
- **field→category map** (`_FIELD_CATEGORY_MAP`, keyed by `(ModelName, field_name)` since `chain`
  repeats): ParseConfig.chain→parser; EnrichConfig.{classifier_chain→classifier, ocr_chain→ocr,
  vlm_chain→vlm}; ChunkConfig.split_method→split_method; SemanticConfig.embed→embed;
  EmbedConfig.{chain,sparse}→embed; RerankConfig.chain→rerank; QueryTransformConfig.llm→llm. A
  `list[Any]` field → `kind=chain` (multi); a scalar `Any` → `kind=provider_union` (optional when it
  admits None). Choices come from `get_configs(category)` reusing availability()/selectable()/
  merge_defaults() (same as DescribeSurface._auto_providers); each choice's `params` = `describe()` of
  the provider config (RECURSE).
- **Wiring:** `discovery/overlays.py` has `CONFIG_BEARING_ROUTES = {create_collection: "pipeline",
  update_config: "patch.pipeline"}`. The router (`_build_config_trees`) describes PipelineConfig once
  per distinct root path using `CONTEXT.registry._cfg`, then sets `config_tree` only on those 2 routes
  (None elsewhere). Cohere rerank id is `cohere_rerank` (NOT `cohere`).
- **Latency caveat:** the describer runs provider `availability()` socket probes (1s timeout each) —
  same as the flat surface. With ~10 unreachable providers this adds ~10s to a cold `/discovery` and
  ~2min to the describer unit test. Acceptable but watch it if more providers are added.
- Exported from `assembly/__init__.py` as `describe_config_tree` (NOT `describe`) because the sibling
  `describe.py` submodule shadows a bare `describe` on `from ...assembly import describe`. Import the
  function directly from `...assembly.config_describer` to be safe.

Verified live on :10020 (collection ce62fdcc…): config_tree carries every gate
(min_score/max_duration_ms/failure_policy/on_degraded enums), full search block (retrieve + nested
grouping/mmr, query_transform.llm provider_union, rerank.chain over bge_server/cohere_rerank),
chunk.split_method→semantic→nested embed union, chunk.atomic 4 bools, embed.sparse optional union.
See [[verbose-error-handling-convention]].
