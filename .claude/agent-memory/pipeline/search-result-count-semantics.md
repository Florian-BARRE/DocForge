---
name: search-result-count-semantics
description: Search rerank/grouping config semantics — request top_k is authoritative; candidate_k is the pre-rerank pool; top_n and grouping.group_by removed
metadata:
  type: project
---

# Search result-count + grouping semantics

Decided 2026-06-25 (search-subsystem audit fixes).

**Result count is the REQUEST `top_k` — full stop.** No search config field may
override it. The engine retrieves a candidate pool (>= top_k, widened for
rerank/MMR/grouping), runs post-steps over the pool, and `_finalize` trims to
`top_k` as the single authoritative trim.

- `search.rerank.candidate_k` = pre-rerank pool size (fed INTO the reranker).
  Engine clamps it up to `top_k` in `_pool_size` so a small candidate_k can never
  starve the final set. `RerankStage.run` re-scores the WHOLE pool and returns it
  sorted — it does NOT trim (the engine owns the trim).
- `search.rerank.top_n` — **REMOVED**. It caused a confusing double-trim
  `min(top_k, top_n)`. `extra="ignore"` keeps stored configs with `top_n` loadable.
- `search.retrieve.grouping.group_by` — **REMOVED** (dead: post.py hardcoded
  grouping by `document_id`). Grouping is always by document. `extra="ignore"`
  keeps stored `group_by` loadable.

**Validator rule:** `search.rerank.enabled == true AND len(chain) == 0` is an
ERROR-severity issue (`code="search.rerank.empty_chain"`), so config/update +
create return 422. Lives in `PipelineChecks._check_rerank_chain`
(common_libs/config/validation/validator/pipeline_checks.py), called from
`check_step_dependencies`. Previously this state silently no-op'd (builder did
`if enabled and chain:`).

**Follow-up (frontend agent):** `app/frontend/src/components/search/panels/RerankSection.tsx`
still renders a `top_n` editor writing an ignored key; should be removed. Any
grouping panel exposing `group_by` likewise.

Discovery endpoint (`/api/v1/discovery`) covers ingestion S0-S6 only — it does NOT
surface the search-config schema, so removed search keys never leaked there.
