// ====== Code Summary ======
// Search Lab override hook — manages the per-query override state for the lab.
// Extracts the baseline from the saved collection config, tracks the user's
// local choices, and computes the diff (only changed fields) as the `overrides`
// object to send with the search request.
//
// Weight handling: weight sliders are initialized to the config baseline
// (content_dense_weight / content_bm25_weight).  Only weights that differ
// from the baseline are included in `weightOverrides`, which is what the
// search request should send.

// ====== Third-Party Library Imports ======
import { useCallback, useMemo, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState } from '../api/types'
import type { SearchBaseline, SearchOverrides } from '../components/search/labTypes'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract the active search baseline from the saved collection config state.
 *
 * Falls back to sensible defaults when sections are absent (hybrid/rrf/none/off).
 *
 * Args:
 *   cfg: Current config state, or null while loading.
 *
 * Returns:
 *   SearchBaseline: The resolved baseline values.
 */
function extractBaseline(cfg: ConfigState | null): SearchBaseline {
  const pipeline = cfg?.pipeline as Record<string, unknown> | undefined
  const searchCfg = (pipeline?.search as Record<string, unknown>) ?? {}
  const retrieve = (searchCfg.retrieve as Record<string, unknown>) ?? {}
  const qt = (searchCfg.query_transform as Record<string, unknown>) ?? {}
  const rerank = (searchCfg.rerank as Record<string, unknown>) ?? {}

  return {
    vector_mode: (retrieve.vector_mode as SearchBaseline['vector_mode'] | undefined) ?? 'hybrid',
    fusion: (retrieve.fusion as SearchBaseline['fusion'] | undefined) ?? 'rrf',
    query_transform_strategy: (qt.strategy as SearchBaseline['query_transform_strategy'] | undefined) ?? 'none',
    rerank_enabled: Boolean(rerank.enabled ?? false),
  }
}

/**
 * Extract weight baselines from the saved config's retrieve section.
 *
 * Maps backend weight keys (content_dense_weight, content_bm25_weight) to the
 * vector names used by the slider UI (content_dense, content_bm25).
 * Defaults to 1.0 when not present — the backend's own default.
 *
 * Args:
 *   cfg: Current config state, or null while loading.
 *
 * Returns:
 *   Record mapping vector name → baseline weight value.
 */
function extractWeightBaseline(cfg: ConfigState | null): Record<string, number> {
  const pipeline = cfg?.pipeline as Record<string, unknown> | undefined
  const retrieve = ((pipeline?.search as Record<string, unknown>)?.retrieve as Record<string, unknown>) ?? {}
  return {
    content_dense: (retrieve.content_dense_weight as number | undefined) ?? 1.0,
    content_bm25:  (retrieve.content_bm25_weight  as number | undefined) ?? 1.0,
  }
}

// ── Public surface ─────────────────────────────────────────────────────────────

/** Public API returned by {@link useLabOverrides}. */
export interface LabOverrideState {
  /** Baseline values from the saved config — drives the "saved config" indicator. */
  baseline: SearchBaseline
  /** What the controls should display (baseline merged with any local changes). */
  display: SearchBaseline
  /**
   * Diff to send in the search request — only fields the user actually changed.
   * Empty object when nothing is overriding the baseline.
   */
  overrides: SearchOverrides
  /** User-set raw weight values (keyed by vector name). */
  localWeights: Record<string, number>
  /**
   * Baseline weights from the collection config (content_dense/content_bm25).
   * Sliders show these as initial values.
   */
  weightBaseline: Record<string, number>
  /**
   * Weight overrides to send in the search request — only weights that differ
   * from the baseline.  Empty object when the user has not changed any weight.
   */
  weightOverrides: Record<string, number>
  /** True when at least one field or weight differs from the config baseline. */
  isOverriding: boolean
  /** Update one field in the local state (triggers override diff). */
  update: <K extends keyof SearchBaseline>(key: K, value: SearchBaseline[K]) => void
  /** Replace the weights map entirely. */
  updateWeights: (weights: Record<string, number>) => void
  /** Reset all overrides and weights — reverts all controls to baseline. */
  reset: () => void
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Manage per-query search override state for the Search Lab.
 *
 * The hook compares the user's local choices against the baseline from the
 * saved collection config.  Only genuinely changed fields appear in `overrides`
 * (and `weightOverrides`), so the backend receives no noise when nothing is
 * overriding the config.
 *
 * Args:
 *   configState: Current collection config, used to derive the baselines.
 *
 * Returns:
 *   LabOverrideState: Reactive state and update callbacks.
 */
export function useLabOverrides(configState: ConfigState | null): LabOverrideState {
  const baseline       = useMemo(() => extractBaseline(configState), [configState])
  const weightBaseline = useMemo(() => extractWeightBaseline(configState), [configState])

  const [local, setLocal]               = useState<Partial<SearchBaseline>>({})
  const [localWeights, setLocalWeights] = useState<Record<string, number>>({})

  // 1. Update a single field in the local state.
  const update = useCallback(<K extends keyof SearchBaseline>(key: K, value: SearchBaseline[K]) => {
    setLocal(prev => ({ ...prev, [key]: value }))
  }, [])

  // 2. Replace the weights map.
  const updateWeights = useCallback((weights: Record<string, number>) => {
    setLocalWeights(weights)
  }, [])

  // 3. Clear all overrides and weights.
  const reset = useCallback(() => {
    setLocal({})
    setLocalWeights({})
  }, [])

  // 4. Merged view — what the controls should render.
  const display: SearchBaseline = useMemo(() => ({ ...baseline, ...local }), [baseline, local])

  // 5. Compute the search-option diff — only fields that genuinely differ from the baseline.
  const overrides: SearchOverrides = useMemo(() => {
    const out: SearchOverrides = {}
    if ('vector_mode' in local && local.vector_mode !== baseline.vector_mode)
      out.vector_mode = local.vector_mode
    if ('fusion' in local && local.fusion !== baseline.fusion)
      out.fusion = local.fusion
    if ('query_transform_strategy' in local && local.query_transform_strategy !== baseline.query_transform_strategy)
      out.query_transform_strategy = local.query_transform_strategy
    if ('rerank_enabled' in local && local.rerank_enabled !== baseline.rerank_enabled)
      out.rerank_enabled = local.rerank_enabled
    return out
  }, [local, baseline])

  // 6. Compute the weight diff — only weights that differ from the config baseline.
  //    Sliders display `localWeights[name] ?? weightBaseline[name]`, so a user
  //    who moves a slider back to the baseline value should not send an override.
  const weightOverrides: Record<string, number> = useMemo(() => {
    const out: Record<string, number> = {}
    for (const [name, val] of Object.entries(localWeights)) {
      const baseVal = weightBaseline[name] ?? 1.0
      if (val !== baseVal) out[name] = val
    }
    return out
  }, [localWeights, weightBaseline])

  const isOverriding =
    Object.keys(overrides).length > 0 || Object.keys(weightOverrides).length > 0

  return {
    baseline,
    display,
    overrides,
    localWeights,
    weightBaseline,
    weightOverrides,
    isOverriding,
    update,
    updateWeights,
    reset,
  }
}
