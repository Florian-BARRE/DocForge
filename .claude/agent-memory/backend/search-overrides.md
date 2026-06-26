---
name: search-overrides
description: Per-REQUEST search overrides (Search Lab) — how the search router shadows pipeline.search for one query without persisting, the merge point, validation, and debug_info.effective shape
metadata:
  type: project
---

The `POST .../documents/search` (+ `/{document_id}/search`) request carries an optional
`overrides` object (`SearchOverrides`, in the search router `models.py`) that shadows the
collection's stored `pipeline.search` for ONE query — never persisted.

**Why:** powers the UI-2 "Search Lab" — tune retrieval live without mutating saved config.
**How to apply:** when touching the search build path or adding a tunable, follow the wiring below.

## Override surface (narrow, all optional)
- `vector_mode` → `pipeline.search.retrieve.vector_mode`
- `fusion` → `pipeline.search.retrieve.fusion`
- `query_transform_strategy` → `pipeline.search.query_transform.strategy`
- `rerank_enabled` → `pipeline.search.rerank.enabled`
- `weights` is the pre-existing top-level request param (kept as-is, NOT in `overrides`).
- Embed provider is ALWAYS auto-derived from `pipeline.embed.chain[0]` — never overridable.

## Merge + validation
- Logic lives in `backend/libs/search/overrides.py` — `SearchOverridesHelpers` (static-only):
  `apply(pipeline_dict, override_keys)` deep-COPIES then maps keys onto `search.*` sub-branches;
  `validate(merged)` parses `PipelineConfig.from_dict` and raises `SearchOverrideError`.
- Router glue = `_resolve_pipeline(collection, overrides, collection_id)` in the search router:
  returns `collection.pipeline` verbatim when overrides omitted/all-None (identical legacy
  behavior); else applies + validates and translates `SearchOverrideError` → HTTP 422.
- `SearchOverrides` uses `extra="forbid"` → a typo'd key is a 422 (never a silent no-op). Bad enum
  values are auto-422 by Pydantic request validation (no manual check needed).
- Two semantic 422 guards (a toggle that would silently no-op): rerank on with empty chain REUSES
  the shared `PipelineChecks.check_step_dependencies` rule `search.rerank.empty_chain`
  (`common_libs.config.validation.validator.pipeline_checks`); transform strategy != "none" with
  `query_transform.llm is None` is a local check. `SearchOverrideError` is NOT a `ValueError`, so it
  stays distinct from `build_search_pipeline`'s `ValueError` (which is the 503 provider-unbuildable path).

## debug_info.effective (debug=True only)
`_to_response_debug` takes the effective `SearchConfig` and adds `debug_info.effective` =
`{vector_mode, fusion, query_transform_strategy, rerank_enabled` (intent, from config)`,
sparse_enabled, candidate_count` (=resolved.candidate_limit)`, query_variants` (count)`,
reranked` (=pipeline_meta.rerank_enabled, actual)`}`. Built by `_effective(config, debug_data)`:
intent from config, runtime facts from `debug_data["resolved"]`/`["pipeline"]`.

## Test wiring note
The API conftest patches `build_search_pipeline` with a fake that builds a real
`SearchPipelineEngine` around mock retrieval from `pipeline_dict["search"]`. Override merge happens
BEFORE that call, so a capturing fake can assert the merged dict; `validate` uses the REAL
PipelineChecks so 422 tests work regardless of the build mock. Debug tests must set
`CONTEXT.retrieval.search_debug = AsyncMock(return_value={resolved,ranked,fused,results})`.
