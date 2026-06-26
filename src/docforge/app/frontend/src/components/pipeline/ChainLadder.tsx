// ====== Code Summary ======
// ChainLadder — expressive fallback ladder for kind="chain" ConfigNode entries.
// Replaces the generic ChainPicker with a visual stack that makes the escalation
// order, gate conditions, and terminal exhaustion policy legible at a glance.
//
// Layout (top-to-bottom):
//   [Gate policy strip — collapsible edit section]
//   Provider 1 card
//   ChainGateDisplay connector (score < X → escalate)
//   Provider 2 card
//   ...
//   Terminal zone (raise = stop+error · continue = degraded)
//   [+ add provider chips]

// ====== Third-Party Library Imports ======
import { useState } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode, ProviderChoice } from '../../api/types'
import { ChainGateDisplay } from './ChainGateDisplay'
import { ProviderCard } from './ProviderCard'

// ── Types ─────────────────────────────────────────────────────────────────────

/** One entry in the chain wire-format array: provider id + flat params. */
interface ChainEntry {
  id: string
  [param: string]: unknown
}

/** Render-prop injected by RecursiveFieldRenderer to render provider sub-params. */
export type RenderChildrenFn = (
  nodes: ConfigNode[],
  readValue: (absPath: string) => unknown,
  writeValue: (absPath: string, v: unknown) => void,
) => ReactNode

interface ChainLadderProps {
  /** The chain ConfigNode from the discovery config_tree. */
  node: ConfigNode
  /**
   * Optional gate sibling ConfigNode (kind=object, path ends with ".gate").
   * When provided, gate settings are shown between providers and can be edited.
   */
  gateNode?: ConfigNode | null
  /** Current ordered list of chain entries from the draft value. */
  value: ChainEntry[] | undefined
  /** Emit the updated chain (providers only — gate is written separately). */
  onChange: (v: ChainEntry[]) => void
  /** Read any absolute path value (used for gate field values). */
  readValue: (absPath: string) => unknown
  /** Write any absolute path value (used for gate field edits). */
  writeValue: (absPath: string, v: unknown) => void
  /** Injected recursive renderer for provider sub-params and gate fields. */
  renderChildren: RenderChildrenFn
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build default param values from a ProviderChoice params list.
 *
 * Args:
 *   params: Child ConfigNode list from a ProviderChoice.
 *
 * Returns:
 *   Record<string, unknown>: last-segment -> default for non-null defaults.
 */
function paramsDefaults(params: ConfigNode[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const p of params) {
    if (p.default !== null && p.default !== undefined) {
      out[p.path.split('.').pop() ?? p.path] = p.default
    }
  }
  return out
}

/**
 * Find a gate field node among the gate object's children by path suffix.
 *
 * Args:
 *   gateNode: The gate object ConfigNode, or null.
 *   suffix:   Path suffix to match (e.g. "min_score", "failure_policy").
 *
 * Returns:
 *   ConfigNode | undefined: Matching child node, or undefined.
 */
function findGateField(gateNode: ConfigNode | null | undefined, suffix: string): ConfigNode | undefined {
  return (gateNode?.children ?? []).find(c => c.path.endsWith(`.${suffix}`))
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Expressive fallback ladder for a chain ConfigNode.
 *
 * Renders providers as a vertical stack in their escalation order with
 * ChainGateDisplay connectors showing the escalation conditions between steps.
 * The terminal zone at the bottom shows the failure_policy (raise = stop with
 * error; continue = produce a degraded result) with on_degraded annotation.
 *
 * An optional collapsible "Gate settings" section lets the user edit all gate
 * fields inline using the existing RecursiveFieldRenderer path.
 *
 * Args:
 *   node:           The chain ConfigNode (available choices, label).
 *   gateNode:       Optional sibling gate object for display and editing.
 *   value:          Current ordered array of chain entries.
 *   onChange:       Callback that receives the updated chain array.
 *   readValue:      Read accessor for absolute dot-path values.
 *   writeValue:     Write accessor for absolute dot-path values.
 *   renderChildren: Injected renderer for provider sub-params and gate children.
 */
export function ChainLadder({
  node, gateNode, value, onChange, readValue, writeValue, renderChildren,
}: ChainLadderProps) {
  const [gateOpen, setGateOpen] = useState(false)
  const chain   = value ?? []
  const choices = node.choices ?? []

  // 1. Read current gate values for the display between steps.
  const minScoreField  = findGateField(gateNode, 'min_score')
  const durationField  = findGateField(gateNode, 'max_duration_ms')
  const policyField    = findGateField(gateNode, 'failure_policy')
  const degradedField  = findGateField(gateNode, 'on_degraded')

  const minScore    = minScoreField  ? (readValue(minScoreField.path)  ?? 0.5)  as number : 0.5
  const maxDuration = durationField  ? (readValue(durationField.path)  ?? null) as number | null : null
  const policy      = policyField    ? (readValue(policyField.path)    ?? 'raise') as string : 'raise'
  const onDegraded  = degradedField  ? (readValue(degradedField.path)  ?? 'empty') as string : 'empty'

  // 2. Derive available (selectable + available) choices for the add strip.
  const available = choices.filter((c: ProviderChoice) => c.available && c.selectable)

  const displayLabel = node.label || (node.path.split('.').pop() ?? node.path)

  // ── Mutation helpers ──────────────────────────────────────────────────────

  function add(c: ProviderChoice) {
    onChange([...chain, { id: c.id, ...paramsDefaults(c.params ?? []) }])
  }

  function remove(idx: number) {
    onChange(chain.filter((_, i) => i !== idx))
  }

  function moveUp(idx: number) {
    if (idx === 0) return
    const next = [...chain]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    onChange(next)
  }

  function moveDown(idx: number) {
    if (idx === chain.length - 1) return
    const next = [...chain]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    onChange(next)
  }

  function writeEntryParam(idx: number, absPath: string, v: unknown) {
    const seg = absPath.split('.').pop() ?? absPath
    onChange(chain.map((item, i) => i === idx ? { ...item, [seg]: v } : item))
  }

  // ── Terminal policy rendering ─────────────────────────────────────────────

  const isRaise = policy === 'raise'
  const terminalClass = isRaise ? 'chain-ladder-terminal chain-ladder-terminal-raise' : 'chain-ladder-terminal chain-ladder-terminal-continue'
  const terminalIcon  = isRaise ? '⛔' : '⚠'
  const terminalMsg   = isRaise
    ? 'Exhausted — pipeline stops with error'
    : `Exhausted — continue with degraded result (${onDegraded})`

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="chain-ladder">
      {/* Header row with label + gate toggle */}
      <div className="chain-ladder-header">
        <span className="chain-ladder-label">{displayLabel}</span>
        {gateNode && (
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 11, padding: '2px 8px' }}
            onClick={() => setGateOpen(o => !o)}
          >
            {gateOpen ? '▲ gate' : '▼ gate'}
          </button>
        )}
      </div>

      {/* Collapsible gate settings form */}
      {gateOpen && gateNode && (
        <div className="chain-ladder-gate-form">
          <div className="chain-ladder-gate-title">Gate settings</div>
          {renderChildren(gateNode.children ?? [], readValue, writeValue)}
        </div>
      )}

      {/* Provider stack with gate connectors between steps */}
      {chain.length > 0 && (
        <div className="chain-ladder-stack">
          {chain.map((item, idx) => {
            const choice = choices.find((c: ProviderChoice) => c.id === item.id)
            return (
              <div key={idx}>
                <ProviderCard
                  rank={idx + 1}
                  entry={item}
                  choice={choice}
                  isFirst={idx === 0}
                  isLast={idx === chain.length - 1}
                  onMoveUp={() => moveUp(idx)}
                  onMoveDown={() => moveDown(idx)}
                  onRemove={() => remove(idx)}
                  renderChildren={renderChildren}
                  readEntry={absPath => {
                    const seg = absPath.split('.').pop() ?? absPath
                    return (item as Record<string, unknown>)[seg]
                  }}
                  writeEntry={(absPath, v) => writeEntryParam(idx, absPath, v)}
                />
                {/* Gate display between providers (not after the last one) */}
                {idx < chain.length - 1 && (
                  <ChainGateDisplay
                    minScore={minScore}
                    maxDurationMs={maxDuration}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Terminal exhaustion policy zone */}
      <div className={terminalClass} title={terminalMsg}>
        <span aria-hidden="true">{terminalIcon}</span>
        <span>{terminalMsg}</span>
      </div>

      {/* Add provider chips */}
      {available.length > 0 && (
        <div className="chain-ladder-add">
          <span className="chain-ladder-add-label">+ add</span>
          {available.map((c: ProviderChoice) => (
            <button
              key={c.id}
              type="button"
              className="chip"
              onClick={() => add(c)}
            >
              {c.label || c.id}
            </button>
          ))}
        </div>
      )}

      {chain.length === 0 && available.length === 0 && (
        <div className="picker-note">No providers available in this deployment.</div>
      )}
    </div>
  )
}
