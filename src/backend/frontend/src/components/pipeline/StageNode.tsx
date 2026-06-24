// ====== Code Summary ======
// Single pipeline stage node — pure display component for both config and trace modes.
// Config mode shows enabled/disabled state with an optional gear hover.
// Trace mode shows a coloured border + duration/metric driven by StageResult.

// ====== Local Project Imports ======
import type { StageDefinition, StageResult } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface StageNodeProps {
  /** Static stage identity and display metadata. */
  stage: StageDefinition
  /** Rendering mode: "config" for pipeline setup, "trace" for live/post-run inspection. */
  mode: 'config' | 'trace'
  /** Runtime result for this stage — only meaningful in trace mode. */
  result?: StageResult
  /** Whether this stage is currently open in the SlidePanel. */
  isActive?: boolean
  /** Called when the user clicks anywhere on the node. */
  onClick: () => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Format a duration in milliseconds into a compact human-readable string.
 *
 * Args:
 *   ms: Duration in milliseconds.
 *
 * Returns:
 *   A string like "1.2s" for values >= 1000 ms, or "850ms" otherwise.
 */
function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${ms}ms`
}

/**
 * Derive the CSS modifier class for the trace-mode border colour.
 *
 * Args:
 *   result: The stage result object, or undefined when not yet run.
 *
 * Returns:
 *   A CSS class name string from the `.stage-node-trace-*` family.
 */
function traceClass(result: StageResult | undefined): string {
  if (!result) return 'stage-node-trace-skipped'
  switch (result.status) {
    case 'done':    return 'stage-node-trace-done'
    case 'running': return 'stage-node-trace-running'
    case 'error':   return 'stage-node-trace-error'
    default:        return 'stage-node-trace-skipped'
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * A single node in the PipelineGraph visualisation.
 *
 * In **config mode** the node reflects whether the stage is enabled or
 * read-only, and shows a gear icon on hover for configurable stages.
 *
 * In **trace mode** the border colour reflects the runtime status
 * (done / running / error / skipped), and the bottom zone shows the
 * wall-clock duration and a short metric string.
 *
 * The component is purely presentational — all data is supplied via props.
 *
 * Args:
 *   stage:    Static stage definition (id, label, icon, flags).
 *   mode:     "config" or "trace" rendering mode.
 *   result:   Optional runtime result used in trace mode.
 *   isActive: Whether the stage is currently selected in a SlidePanel.
 *   onClick:  Callback for click events on the node.
 */
export function StageNode({ stage, mode, result, isActive, onClick }: StageNodeProps) {
  // 1. Build the list of CSS class modifiers for the node container.
  const classes = ['stage-node']
  if (isActive) classes.push('stage-node-active')
  if (stage.optional) classes.push('stage-node-optional')
  if (stage.readOnly) classes.push('stage-node-readonly')
  if (mode === 'trace') classes.push(traceClass(result))

  // 2. Derive the status zone content depending on mode.
  const statusContent = mode === 'config'
    ? _renderConfigStatus(stage)
    : _renderTraceStatus(result)

  return (
    <div
      className={classes.join(' ')}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick() }}
      aria-label={`${stage.label} stage`}
      aria-pressed={isActive}
    >
      {/* Icon */}
      <span className="stage-node-icon" aria-hidden="true">{stage.icon}</span>

      {/* Label */}
      <span className="stage-node-label">{stage.label}</span>

      {/* Bottom status zone */}
      <div className="stage-node-status">{statusContent}</div>

      {/* Gear overlay — only in config mode for non-read-only stages */}
      {mode === 'config' && !stage.readOnly && (
        <span className="stage-node-config-gear" aria-hidden="true">⚙</span>
      )}

      {/* Read-only badge */}
      {stage.readOnly && (
        <span className="stage-node-readonly-badge" aria-label="read-only">ro</span>
      )}
    </div>
  )
}

// ── Private render helpers ────────────────────────────────────────────────────

/**
 * Render the status zone for config mode.
 *
 * Args:
 *   stage: The stage definition, used to check the readOnly flag.
 *
 * Returns:
 *   A JSX element indicating whether the stage is enabled or read-only.
 */
function _renderConfigStatus(stage: StageDefinition) {
  if (stage.readOnly) {
    return <span className="stage-node-status-readonly">read-only</span>
  }
  if (stage.optional) {
    return <span className="stage-node-status-optional">optional</span>
  }
  return <span className="stage-node-status-enabled">enabled</span>
}

/**
 * Render the status zone for trace mode.
 *
 * Args:
 *   result: The stage result, or undefined when the stage has not yet run.
 *
 * Returns:
 *   A JSX element with duration and metric text, or a dimmed placeholder.
 */
function _renderTraceStatus(result: StageResult | undefined) {
  // 1. No result yet — show a neutral placeholder.
  if (!result) {
    return <span className="stage-node-status-pending">—</span>
  }

  // 2. Error state — show only the error indicator, no metric.
  if (result.status === 'error') {
    return <span className="stage-node-status-error">error</span>
  }

  // 3. Running state — animated dots.
  if (result.status === 'running') {
    return <span className="stage-node-status-running pulse">…</span>
  }

  // 4. Done / skipped — show duration and optional metric.
  return (
    <>
      {result.duration_ms !== undefined && (
        <span className="stage-node-status-duration">
          {formatDuration(result.duration_ms)}
        </span>
      )}
      {result.metric && (
        <span className="stage-node-status-metric">{result.metric}</span>
      )}
      {result.status === 'skipped' && (
        <span className="stage-node-status-skipped">skip</span>
      )}
    </>
  )
}
