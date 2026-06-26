// ====== Code Summary ======
// Search Lab override hook — manages the per-query override state for the lab.
// Extracts the baseline from the saved collection config, tracks the user's
// local choices, and computes the diff (only changed fields) as the `overrides`
// object to send with the search request.

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
  /** User-set weights (send as `weights` in the search request when non-empty). */
  localWeights: Record<string, number>
  /** True when at least one field or weight differs from the baseline. */
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
 * saved collection config. Only genuinely changed fields appear in `overrides`,
 * so the backend receives no noise when nothing is overriding the config.
 *
 * Args:
 *   configState: Current collection config, used to derive the baseline.
 *
 * Returns:
 *   LabOverrideState: Reactive state and update callbacks.
 */
export function useLabOverrides(configState: ConfigState | null): LabOverrideState {
  const baseline = useMemo(() => extractBaseline(configState), [configState])
  const [local, setLocal] = useState<Partial<SearchBaseline>>({})
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

  // 5. Compute the diff — only fields that genuinely differ from the baseline.
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

  const isOverriding = Object.keys(overrides).length > 0 || Object.keys(localWeights).length > 0

  return { baseline, display, overrides, localWeights, isOverriding, update, updateWeights, reset }
}
