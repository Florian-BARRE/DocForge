// ====== Code Summary ======
// StageFlowNode — rich pipeline stage card for the new PipelineFlowGraph.
// Config mode: shows provider summary, description, status pill, gear hover.
// Trace mode: shows runtime status color + duration + metric in the footer.
// Replaces the old StageNode with more information density and modern styling.

// ====== Internal Project Imports ======
import type { ConfigState } from '../../api/types'
import type { StageDefinition, StageResult, StageStatus } from './types'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Extract a one-line provider summary from the collection's config state.
 *
 * Reads the pipeline sub-object at the stage's fieldPathPrefix and returns a
 * compact label: chain summary (e.g. "docling +1"), provider id, or key scalar.
 *
 * Args:
 *   configState: Current persisted config for the collection.
 *   prefix:      Stage fieldPathPrefix (e.g. "pipeline.parse").
 *
 * Returns:
 *   string | null: Compact label, or null when no summary can be derived.
 */
function extractStageSummary(configState: ConfigState | null, prefix: string): string | null {
  if (!configState) return null
  // 1. Walk the prefix segments into the config object.
  const parts = prefix.split('.')
  let cursor: unknown = configState
  for (const part of parts) {
    if (cursor && typeof cursor === 'object') {
      cursor = (cursor as Record<string, unknown>)[part]
    } else return null
  }
  if (!cursor || typeof cursor !== 'object') return null
  const cfg = cursor as Record<string, unknown>

  // 2. Chain array: show first provider + overflow count.
  if (Array.isArray(cfg.chain) && cfg.chain.length > 0) {
    const chain = cfg.chain as Array<{ id?: string }>
    const first = chain[0]?.id ?? '?'
    return chain.length > 1 ? `${first}  +${chain.length - 1}` : first
  }

  // 3. Explicit enabled flag.
  if (typeof cfg.enabled === 'boolean') return cfg.enabled ? 'enabled' : 'disabled'

  // 4. Chunk split_method as a key signal.
  if (typeof cfg.split_method === 'string') return cfg.split_method

  return null
}

/**
 * Map a StageStatus to its CSS modifier class for trace-mode border color.
 *
 * Args:
 *   status: Stage lifecycle status.
 *
 * Returns:
 *   string: CSS class name from the .stage-flow-node-trace-* family.
 */
function traceClass(status: StageStatus): string {
  switch (status) {
    case 'done':    return 'stage-flow-node-trace-done'
    case 'running': return 'stage-flow-node-trace-running'
    case 'error':   return 'stage-flow-node-trace-error'
    default:        return 'stage-flow-node-trace-skipped'
  }
}

/**
 * Format a duration in milliseconds into a compact human-readable string.
 *
 * Args:
 *   ms: Duration in milliseconds.
 *
 * Returns:
 *   string: e.g. "1.2s" or "850ms".
 */
function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface StageFlowNodeProps {
  /** Static stage identity and display metadata. */
  stage: StageDefinition
  /** Rendering mode: "config" for pipeline setup, "trace" for post-run inspection. */
  mode: 'config' | 'trace'
  /** Runtime result for this stage — only meaningful in trace mode. */
  result?: StageResult
  /** Whether this stage is currently selected in the detail panel. */
  isActive: boolean
  /** Called when the user clicks the card. */
  onClick: () => void
  /** Collection config state — used to derive provider summaries in config mode. */
  configState?: ConfigState | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Rich stage card for the pipeline flow graph.
 *
 * Config mode: displays stage ID badge, icon, label, description, and a
 * one-line provider summary derived from the collection's config state.
 *
 * Trace mode: replaces the summary/pill footer with a runtime status
 * (done/running/error/skipped), wall-clock duration, and a short metric.
 *
 * Args:
 *   stage:       Static stage definition.
 *   mode:        "config" or "trace" rendering mode.
 *   result:      Optional runtime trace result.
 *   isActive:    Whether this stage's detail panel is open.
 *   onClick:     Click handler.
 *   configState: Optional live config used for the provider summary.
 */
export function StageFlowNode({
  stage, mode, result, isActive, onClick, configState,
}: StageFlowNodeProps) {
  // 1. Build CSS class list.
  const classes = ['stage-flow-node']
  if (isActive) classes.push('stage-flow-node-active')
  if (stage.optional) classes.push('stage-flow-node-optional')
  if (stage.readOnly) classes.push('stage-flow-node-readonly')
  if (mode === 'trace' && result) classes.push(traceClass(result.status))

  // 2. Derive footer content by mode.
  const summary = extractStageSummary(configState ?? null, stage.fieldPathPrefix)
  const footer = mode === 'config'
    ? _configFooter(stage, summary)
    : _traceFooter(result)

  // 3. Stage ID badge label (e.g. "S1", "S4").
  const idLabel = stage.id.toUpperCase()

  return (
    <div
      className={classes.join(' ')}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick() }}
      aria-label={`${stage.label} stage`}
      aria-pressed={isActive}
    >
      {/* Top row: ID badge + icon */}
      <div className="stage-flow-node-top">
        <span className="stage-flow-node-id">{idLabel}</span>
        <span className="stage-flow-node-icon" aria-hidden="true">{stage.icon}</span>
      </div>

      {/* Stage label */}
      <span className="stage-flow-node-label">{stage.label}</span>

      {/* Description — muted, truncated at 2 lines */}
      {stage.description && (
        <span className="stage-flow-node-desc">{stage.description}</span>
      )}

      {/* Footer: provider summary + status pill (config) or trace info */}
      <div className="stage-flow-node-footer">
        {footer}
      </div>

      {/* Gear hover overlay — config mode, non-read-only stages only */}
      {mode === 'config' && !stage.readOnly && (
        <span className="stage-flow-node-gear" aria-hidden="true">&#x2699;</span>
      )}
    </div>
  )
}

// ── Private render helpers ────────────────────────────────────────────────────

function _configFooter(stage: StageDefinition, summary: string | null) {
  const pillClass = stage.optional
    ? 'stage-flow-node-pill stage-flow-node-pill-optional'
    : 'stage-flow-node-pill stage-flow-node-pill-enabled'
  const pillLabel = stage.optional ? 'opt-in' : 'on'

  return (
    <>
      {summary ? (
        <span className="stage-flow-node-summary" title={summary}>{summary}</span>
      ) : (
        <span className="stage-flow-node-summary" />
      )}
      <span className={pillClass}>{pillLabel}</span>
    </>
  )
}

function _traceFooter(result: StageResult | undefined) {
  if (!result) {
    return <span className="stage-flow-node-trace-label stage-flow-node-trace-label-dim">—</span>
  }
  if (result.status === 'error') {
    return <span className="stage-flow-node-trace-label stage-flow-node-trace-label-err">error</span>
  }
  if (result.status === 'running') {
    return <span className="stage-flow-node-trace-label stage-flow-node-trace-label-run">running…</span>
  }
  return (
    <>
      {result.duration_ms !== undefined && (
        <span className="stage-flow-node-summary">{formatDuration(result.duration_ms)}</span>
      )}
      {result.metric && (
        <span className="stage-flow-node-trace-label stage-flow-node-trace-label-dim">
          {result.metric}
        </span>
      )}
      {result.status === 'skipped' && (
        <span className="stage-flow-node-trace-label stage-flow-node-trace-label-dim">skip</span>
      )}
    </>
  )
}
