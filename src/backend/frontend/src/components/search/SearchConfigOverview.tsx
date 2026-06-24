// ====== Code Summary ======
// SearchConfigOverview — read-only summary card shown in the search inline panel
// when no stage is selected.  Displays the active query-transform strategy, the
// retrieval vector mode + fusion, and reranking status.  Embed info is
// intentionally omitted — click the Embed node to see it.

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
  const qtCfg = (searchCfg.query_transform as Record<string, unknown>) ?? {}
  const strategy = (qtCfg.strategy as string | undefined) ?? 'none'
  const retrieveCfg = (searchCfg.retrieve as Record<string, unknown>) ?? {}
  const vectorMode = (retrieveCfg.vector_mode as string | undefined) ?? 'hybrid'
  const fusion = (retrieveCfg.fusion as string | undefined) ?? 'rrf'
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

      {/* Vector mode */}
      <div className="stage-panel-row">
        <span className="stage-panel-label">Vector mode</span>
        <span className="stage-panel-value">{vectorMode}</span>
      </div>

      {/* Fusion */}
      <div className="stage-panel-row">
        <span className="stage-panel-label">Fusion</span>
        <span className="stage-panel-value">{fusion}</span>
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
