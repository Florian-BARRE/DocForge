---
name: search-pipeline-antipatterns
description: Recurring correctness/coherence issues in the P7 search pipeline (engine, rerank, fusion) — check these on any search-related review
metadata:
  type: feedback
---

Anti-patterns to check on every review touching `libs/search/pipeline/` or `libs/search/field_index/helpers.py`.

**Why:** caught during the P7b search-pipeline review; these are subtle and recur because the knobs are independent and the defaults mask the interaction.

**How to apply:** when reviewing search engine / fusion code, actively verify each:

1. **top_n / top_k / candidate_k underdelivery.** `RerankConfig.top_n` and `RerankConfig.candidate_k` are independent of the request `top_k`. `RerankStage.run` trims to `top_n`; `engine._pool_size` uses `candidate_k` (not `max(candidate_k, top_k)`); `engine._finalize` trims to `top_k`. A caller asking `top_k=100` with collection `top_n=10`/`candidate_k=50` silently gets ≤10 results. Flag when these three are not reconciled.

2. **Stale docstrings claiming attribute mutation.** `SearchResult` is `@dataclass(slots=True)` with no `metadata`/`rerank_score` field. `RerankStage` docstrings claim they attach `rerank_score` to result metadata — false, and `slots=True` would make it raise. Verify any "attaches X to result" docstring against the actual dataclass fields.

3. **DBSF zero-span vectors.** `FieldIndexHelpers.dbsf_fuse`: when a vector returns 1 candidate or all-equal scores, `span<=0` → `norm=0.0` → that vector contributes nothing, so a lone strong hit can vanish. RRF (rank-based) is immune. Recommend `norm=1.0`/`0.5` on zero-span.

4. **score_threshold cross-family.** A single `score_threshold` is passed to both dense (cosine ~0-1) and sparse (BM25 unbounded) `query_points` — meaningless for both at once. OK because default is None; only relevant for single-family modes.

5. **Encoding mojibake.** `rerank.py` was saved Latin-1 (`â€”` instead of `—`). Grep for `â€` on new search files.
