// ====== Code Summary ======
// SearchSettingsBar — compact one-line row of chips summarising the currently
// active search configuration (vector mode, fusion, query transform, rerank).
// Read from the persisted collection config (pipeline.search). Rendered next to
// the query bar so the user always knows in which "mode" they are searching.

// ====== Third-Party Library Imports ======
import type { ConfigState } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchSettingsBarProps {
  /** Current persisted config state for the collection, or null while loading. */
  configState: ConfigState | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Compact summary of the active search settings as a wrapping row of chips.
 *
 * Reads pipeline.search from configState and renders short French chips with
 * explanatory tooltips. When a section is missing, falls back to defaults
 * (hybrid / rrf / none / rerank off) so the bar always reflects the real
 * behaviour the backend will apply.
 *
 * Args:
 *   configState: Current collection config state, or null while loading.
 */
export function SearchSettingsBar({ configState }: SearchSettingsBarProps) {
  // 1. Extract the pipeline.search sub-object (tolerant to missing sections).
  const pipeline = configState?.pipeline as Record<string, unknown> | undefined
  const searchCfg = (pipeline?.search as Record<string, unknown>) ?? {}

  // 2. Derive the four display values, falling back to defaults.
  const retrieveCfg = (searchCfg.retrieve as Record<string, unknown>) ?? {}
  const vectorMode = (retrieveCfg.vector_mode as string | undefined) ?? 'hybrid'
  const fusion = (retrieveCfg.fusion as string | undefined) ?? 'rrf'

  const qtCfg = (searchCfg.query_transform as Record<string, unknown>) ?? {}
  const strategy = (qtCfg.strategy as string | undefined) ?? 'none'

  const rerankCfg = (searchCfg.rerank as Record<string, unknown>) ?? {}
  const rerankEnabled = Boolean(rerankCfg.enabled ?? false)

  // 3. Render the chips. Transform chip only appears when a strategy is active.
  return (
    <div className="search-settings-bar">
      {/* Vector mode — which vectors are queried */}
      <span className="tag" title="Vecteurs interrogés">
        Mode : {vectorModeLabel(vectorMode)}
      </span>

      {/* Fusion — how the per-vector rankings are combined */}
      <span className="tag" title="Méthode de combinaison des classements">
        Fusion : {fusionLabel(fusion)}
      </span>

      {/* Query transform — only when a transform strategy is active */}
      {strategy !== 'none' && (
        <span className="tag tag-done" title="Transformation de la requête avant recherche">
          Transform : {strategyLabel(strategy)}
        </span>
      )}

      {/* Rerank — only shown as an active badge when enabled */}
      {rerankEnabled && (
        <span className="tag tag-done" title="Reclassement des résultats par un cross-encoder">
          rerank
        </span>
      )}
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Translate a vector mode identifier to a short French label.
 *
 * Args:
 *   mode: Vector mode identifier (hybrid / dense / sparse).
 *
 * Returns:
 *   string: Human-readable French label.
 */
function vectorModeLabel(mode: string): string {
  if (mode === 'dense') return 'dense'
  if (mode === 'sparse') return 'sparse'
  return 'hybride'
}

/**
 * Translate a fusion identifier to a short uppercase French label.
 *
 * Args:
 *   fusion: Fusion identifier (rrf / dbsf).
 *
 * Returns:
 *   string: Human-readable label.
 */
function fusionLabel(fusion: string): string {
  if (fusion === 'dbsf') return 'DBSF'
  return 'RRF'
}

/**
 * Translate a query-transform strategy identifier to a short French label.
 *
 * Args:
 *   strategy: Transform strategy identifier (rewrite / hyde / multi_query).
 *
 * Returns:
 *   string: Human-readable French label, or the raw value when unknown.
 */
function strategyLabel(strategy: string): string {
  if (strategy === 'rewrite') return 'réécriture'
  if (strategy === 'hyde') return 'HyDE'
  if (strategy === 'multi_query') return 'multi-requête'
  return strategy
}
