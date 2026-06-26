// ====== Code Summary ======
// Shared types for the Search Lab — per-query override model and the
// `effective` envelope returned by the backend in debug_info.

// ── Baseline ──────────────────────────────────────────────────────────────────

/** Search settings as saved in the collection's pipeline config. */
export interface SearchBaseline {
  vector_mode: 'dense' | 'sparse' | 'hybrid'
  fusion: 'rrf' | 'dbsf'
  query_transform_strategy: 'none' | 'rewrite' | 'hyde' | 'multi_query'
  rerank_enabled: boolean
}

// ── Overrides ─────────────────────────────────────────────────────────────────

/**
 * Per-query overrides that shadow the collection's saved search config.
 * Only send keys that the user actually changed vs the baseline.
 * Mirrors the backend SearchOverrides Pydantic model.
 */
export interface SearchOverrides {
  vector_mode?: 'dense' | 'sparse' | 'hybrid'
  fusion?: 'rrf' | 'dbsf'
  query_transform_strategy?: 'none' | 'rewrite' | 'hyde' | 'multi_query'
  rerank_enabled?: boolean
}

// ── Effective (from backend debug_info) ───────────────────────────────────────

/**
 * The `effective` sub-object returned inside `debug_info` when debug=true.
 * Reflects the actual settings the backend applied for the query (baseline
 * merged with any overrides).
 */
export interface SearchEffective {
  vector_mode?: string
  fusion?: string
  query_transform_strategy?: string
  rerank_enabled?: boolean
  sparse_enabled?: boolean
  candidate_count?: number
  query_variants?: string[]
  reranked?: boolean
}
