// ====== Code Summary ======
// StageFlowNode — react-flow custom node for the PipelineCanvas.
// Renders a polished elevated card with a 3 px per-stage accent strip, stage ID
// badge, icon, label, role description, provider/chain chip, ON/OPT-IN status
// pill, and source/target Handles styled as subtle 8 px dots.
// All colors come from CSS custom properties — no hardcoded values.

// ====== Third-Party Library Imports ======
import { Handle, Position } from '@xyflow/react'
import type { Node, NodeProps } from '@xyflow/react'

// ====== Internal Project Imports ======
import type { ConfigState } from '../../api/types'
import type { StageDefinition, StageResult, StageStatus } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Data payload carried on each react-flow node in the pipeline canvas. */
export interface StageNodeData extends Record<string, unknown> {
  /** Static stage identity and display metadata. */
  stage: StageDefinition
  /** Canvas rendering mode. */
  mode: 'config' | 'trace'
  /** Runtime result — populated in trace mode only. */
  result?: StageResult
  /** Whether this stage's config/trace panel is currently open. */
  isActive: boolean
  /** Live collection config — used to derive provider summaries. */
  configState: ConfigState | null
}

/** Typed react-flow node variant used in PipelineCanvas. */
export type StageFlowNodeType = Node<StageNodeData>

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Map a stage id to an accent color CSS-var reference for the top strip.
 * All values reference existing custom properties — no hardcoded hex values.
 */
const STAGE_ACCENT: Record<string, string> = {
  s0:        'var(--s-info)',
  s1:        'var(--accent)',
  s2:        'var(--s-warning)',
  s4:        'var(--s-done)',
  s5:        'var(--s-info)',
  s6:        'var(--accent)',
  transform: 'var(--s-info)',
  retrieve:  'var(--s-done)',
  rerank:    'var(--accent)',
}

/**
 * Extract a one-line provider summary from the collection config.
 *
 * Walks the fieldPathPrefix into the config and returns a compact chip label:
 * first chain provider + "×N" count, enabled flag, or split_method.
 *
 * Args:
 *   config: Live persisted config for the collection, or null.
 *   prefix: Stage fieldPathPrefix (e.g. "pipeline.parse").
 *
 * Returns:
 *   string | null: Compact summary, or null when not derivable.
 */
function extractSummary(config: ConfigState | null, prefix: string): string | null {
  if (!config) return null
  const parts = prefix.split('.')
  let cursor: unknown = config
  for (const part of parts) {
    if (cursor && typeof cursor === 'object') cursor = (cursor as Record<string, unknown>)[part]
    else return null
  }
  if (!cursor || typeof cursor !== 'object') return null
  const cfg = cursor as Record<string, unknown>
  if (Array.isArray(cfg.chain) && cfg.chain.length > 0) {
    const chain = cfg.chain as Array<{ id?: string }>
    const first = chain[0]?.id ?? '?'
    return chain.length > 1 ? `${first} ×${chain.length}` : first
  }
  if (typeof cfg.enabled === 'boolean') return cfg.enabled ? 'enabled' : 'disabled'
  if (typeof cfg.split_method === 'string') return cfg.split_method
  return null
}

/**
 * Map a StageStatus to its CSS modifier class for the card border.
 *
 * Args:
 *   status: The stage's lifecycle status.
 *
 * Returns:
 *   CSS class name from the .sfn-trace-* family.
 */
function traceModifier(status: StageStatus): string {
  switch (status) {
    case 'done':    return 'sfn-trace-done'
    case 'running': return 'sfn-trace-running'
    case 'error':   return 'sfn-trace-error'
    default:        return 'sfn-trace-skipped'
  }
}

/**
 * Format a duration in milliseconds as a compact human-readable string.
 *
 * Args:
 *   ms: Duration in milliseconds.
 *
 * Returns:
 *   "1.2s" for durations >= 1 s, "850ms" otherwise.
 */
function formatDuration(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

// ── Sub-renderers ─────────────────────────────────────────────────────────────

function ConfigFooter({ stage, summary }: { stage: StageDefinition; summary: string | null }) {
  const pillCls = stage.optional ? 'sfn-pill sfn-pill-opt' : 'sfn-pill sfn-pill-on'
  return (
    <>
      {summary
        ? <span className="sfn-summary" title={summary}>{summary}</span>
        : <span className="sfn-summary" />
      }
      <span className={pillCls}>{stage.optional ? 'opt-in' : 'on'}</span>
    </>
  )
}

function TraceFooter({ result }: { result?: StageResult }) {
  if (!result)                     return <span className="sfn-tdim">—</span>
  if (result.status === 'error')   return <span className="sfn-terr">error</span>
  if (result.status === 'running') return <span className="sfn-trun">running…</span>
  return (
    <>
      {result.duration_ms !== undefined &&
        <span className="sfn-tdur">{formatDuration(result.duration_ms)}</span>}
      {result.metric && <span className="sfn-tmet">{result.metric}</span>}
      {result.status === 'skipped' && <span className="sfn-tdim">skip</span>}
    </>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * React Flow custom node for a single pipeline stage.
 *
 * Renders an elevated card with a 3 px per-stage accent strip, stage ID badge,
 * icon, label, role description, and a footer row with either a provider/chain
 * chip + status pill (config mode) or trace status + duration (trace mode).
 * Left/right Handles are 8 px subtle dots via the sfn-handle CSS class.
 *
 * Args (react-flow NodeProps):
 *   data.stage:       Static stage definition.
 *   data.mode:        Canvas rendering mode ("config" | "trace").
 *   data.result:      Optional runtime trace result.
 *   data.isActive:    Whether this stage's detail panel is currently open.
 *   data.configState: Live collection config for provider summary derivation.
 */
export function StageFlowNode({ data }: NodeProps<StageFlowNodeType>) {
  const { stage, mode, result, isActive, configState } = data

  // 1. Build the card's CSS modifier class list.
  const classes = ['sfn-card']
  if (isActive)        classes.push('sfn-active')
  if (stage.optional)  classes.push('sfn-optional')
  if (stage.readOnly)  classes.push('sfn-readonly')
  if (mode === 'trace' && result) classes.push(traceModifier(result.status))

  // 2. Derive per-stage accent (CSS var reference — no hardcoded hex).
  const accentColor = STAGE_ACCENT[stage.id] ?? 'var(--accent)'

  // 3. Derive provider/chain summary chip text.
  const summary = extractSummary(configState, stage.fieldPathPrefix)

  return (
    <div className={classes.join(' ')}>
      {/* Left handle — edge entry point from the preceding stage. */}
      <Handle type="target" position={Position.Left}
        className="sfn-handle" isConnectable={false} />

      {/* 3 px accent strip — per-stage hue, top of card. */}
      <div className="sfn-accent-strip" style={{ background: accentColor }} />

      {/* Top row: stage ID badge (mono) + icon flush right. */}
      <div className="sfn-top">
        <span className="sfn-id">{stage.id.toUpperCase()}</span>
        <span className="sfn-icon" aria-hidden="true">{stage.icon}</span>
      </div>

      {/* Stage name — Inter 600. */}
      <span className="sfn-label">{stage.label}</span>

      {/* Role description — muted, clamped to 2 lines. */}
      {stage.description && (
        <span className="sfn-desc">{stage.description}</span>
      )}

      {/* Footer: provider chip + pill (config) or trace status + duration. */}
      <div className="sfn-footer">
        {mode === 'config'
          ? <ConfigFooter stage={stage} summary={summary} />
          : <TraceFooter result={result} />
        }
      </div>

      {/* Right handle — edge exit point to the following stage. */}
      <Handle type="source" position={Position.Right}
        className="sfn-handle" isConnectable={false} />
    </div>
  )
}
