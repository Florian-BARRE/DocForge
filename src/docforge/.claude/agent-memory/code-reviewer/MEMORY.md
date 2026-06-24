# Code Reviewer Memory — DocForge

- [Search Pipeline Anti-Patterns](search_pipeline_antipatterns.md) — top_n/top_k/candidate_k underdelivery, stale docstrings, DBSF zero-span
- [Reindex/Staleness Coherence](reindex_staleness_coherence.md) — reindex_diff is bidirectional; transient _reindex_reasons attr is fragile
- [Secret Round-Trip Pattern](secret_roundtrip.md) — how merge_patch preserves redacted secrets (validated, do not flag as a bug)
- [Layer DAG Rules](layer_dag.md) — storage(2) must only import search.field_index, never search.hybrid/pipeline
- [Page Indexing Is 0-Based](page_indexing_zero_based.md) — pages/screenshot are 0-indexed end to end; page 1 != first page (off-by-one trap)
