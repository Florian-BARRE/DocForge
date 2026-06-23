// ====== Code Summary ======
// SearchConfigOverview — read-only summary card shown in the search inline panel
// when no stage is selected.  Displays the active strategy, top_k, and reranking
// status.  Embed info is intentionally omitted — click the Embed node to see it.

// ====== Third-Party Library Imports ======
import type { ConfigState } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchConfigOverviewProps {
  /** Current persisted config state for the collection. */
  configState: ConfigState | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Read-only overview of the current search configuration.
 *
 * Extracts the most relevant search settings from configState and renders them
 * as a compact key/value card.  Intended as the default view in the inline panel
 * before the user selects a specific stage to configure.
 *
 * Args:
 *   configState: Current collection config state, or null while loading.
 */
export function SearchConfigOverview({ configState }: SearchConfigOverviewProps) {
  // 1. Extract pipeline.search sub-object.
  const pipeline = configState?.pipeline as Record<string, unknown> | undefined
  const searchCfg = (pipeline?.search as Record<string, unknown>) ?? {}

  // 2. Derive display values from nested search config.
  const strategy = (searchCfg.strategy as string | undefined) ?? 'none'
  const retrieveCfg = (searchCfg.retrieve as Record<string, unknown>) ?? {}
  const topK = (retrieveCfg.top_k as number | undefined) ?? 10
  const rerankCfg = (searchCfg.rerank as Record<string, unknown>) ?? {}
  const rerankEnabled = Boolean(rerankCfg.enabled ?? false)

  return (
    <div className="search-overview-card">
      {/* Section title */}
      <div className="search-overview-title">Search configuration</div>

      {/* Strategy */}
      <div className="stage-panel-row">
        <span className="stage-panel-label">Strategy</span>
        <span className={`tag ${strategyTagClass(strategy)}`}>{strategy}</span>
      </div>

      {/* Top K */}
      <div className="stage-panel-row">
        <span className="stage-panel-label">Top K</span>
        <span className="stage-panel-value">{topK}</span>
      </div>

      {/* Reranking status */}
      <div className="stage-panel-row">
        <span className="stage-panel-label">Reranking</span>
        <span className={`tag ${rerankEnabled ? 'tag-done' : ''}`}>
          {rerankEnabled ? 'enabled' : 'disabled'}
        </span>
      </div>

      {/* Hint */}
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
        Click a stage to configure it.
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Map a strategy string to a CSS tag modifier class.
 *
 * The `none` strategy uses the default grey tag; all active strategies
 * use the accent (done) colour to indicate an active transform.
 *
 * Args:
 *   strategy: Active transform strategy identifier.
 *
 * Returns:
 *   string: CSS class name to apply alongside `.tag`.
 */
function strategyTagClass(strategy: string): string {
  if (strategy === 'none') return ''
  return 'tag-done'
}
