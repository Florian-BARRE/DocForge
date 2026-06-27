// ====== Code Summary ======
// ChainLadder — restructured fallback ladder for kind="chain" ConfigNode entries.
//
// Rendered in three clearly-labelled sections:
//   1. "Providers — tried in order" — provider stack with role badges + gate connectors
//   2. "If all providers fail"       — FailurePolicyControl (calm segmented control)
//   3. "Quality & limits"            — GateLimits (always-visible escalation thresholds)
//
// The old red "Exhausted" terminal bar and the hidden "gate" toggle are gone.
// Gate settings are now always visible in sections 2 and 3.

// ====== Third-Party Library Imports ======
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode, ProviderChoice } from '../../api/types'
import { ChainGateDisplay } from './ChainGateDisplay'
import { FailurePolicyControl } from './FailurePolicyControl'
import { GateLimits } from './GateLimits'
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
   * When provided, sections 2 (failure policy) and 3 (quality limits) are shown.
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
  /** Injected recursive renderer for provider sub-params. */
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
 * Three-section fallback ladder for a chain ConfigNode.
 *
 * Section 1 shows providers in order with role badges ("Primary", "Fallback N")
 * and plain-language gate connectors between steps. Section 2 exposes the
 * failure_policy as a calm segmented control (no more red error bar). Section 3
 * shows quality/timeout thresholds that were previously hidden behind a toggle.
 *
 * Args:
 *   node:           The chain ConfigNode (available choices, label).
 *   gateNode:       Optional sibling gate object for sections 2 and 3.
 *   value:          Current ordered array of chain entries.
 *   onChange:       Callback that receives the updated chain array.
 *   readValue:      Read accessor for absolute dot-path values.
 *   writeValue:     Write accessor for absolute dot-path values.
 *   renderChildren: Injected renderer for provider sub-params.
 */
export function ChainLadder({
  node, gateNode, value, onChange, readValue, writeValue, renderChildren,
}: ChainLadderProps) {
  const chain   = value ?? []
  const choices = node.choices ?? []

  // 1. Read current gate field nodes and their values.
  const minScoreField = findGateField(gateNode, 'min_score')
  const durationField = findGateField(gateNode, 'max_duration_ms')
  const policyField   = findGateField(gateNode, 'failure_policy')
  const degradedField = findGateField(gateNode, 'on_degraded')

  const minScore    = minScoreField ? (readValue(minScoreField.path) ?? 0) as number : 0
  const maxDuration = durationField ? (readValue(durationField.path) ?? null) as number | null : null
  const policy      = policyField   ? (readValue(policyField.path)   ?? 'raise') as string : 'raise'
  const onDegraded  = degradedField ? (readValue(degradedField.path) ?? 'empty') as string : 'empty'

  // 2. Available (selectable + available) choices for the "add" strip.
  const available = choices.filter((c: ProviderChoice) => c.available && c.selectable)

  // ── Mutation helpers ────────────────────────────────────────────────────────

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

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="chain-ladder">
      {/* ── Section 1: Providers — tried in order ───────────────────────────── */}
      <div className="chain-section" style={{ borderTop: 'none', paddingTop: 0 }}>
        <div className="chain-section-head">
          <span className="chain-section-title">Providers — tried in order</span>
          <span className="chain-section-hint">
            DocForge runs the first provider; if it fails or returns low quality, it falls back to the next.
          </span>
        </div>

        {chain.length === 0 && available.length === 0 && (
          <div className="picker-note">No providers available in this deployment.</div>
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
                  {/* Gate connector between providers (not after the last one) */}
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

        {/* Add fallback provider chips */}
        {available.length > 0 && (
          <div className="chain-ladder-add">
            <span className="chain-ladder-add-label">
              {chain.length === 0 ? 'Add a provider:' : 'Add fallback provider:'}
            </span>
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
      </div>

      {/* ── Section 2: If all providers fail ────────────────────────────────── */}
      {gateNode && (
        <FailurePolicyControl
          policyNode={policyField}
          degradedNode={degradedField}
          policy={policy}
          onDegraded={onDegraded}
          writeValue={writeValue}
        />
      )}

      {/* ── Section 3: Quality & limits ─────────────────────────────────────── */}
      {gateNode && (
        <GateLimits
          minScoreNode={minScoreField}
          durationNode={durationField}
          minScore={minScore}
          maxDurationMs={maxDuration}
          writeValue={writeValue}
        />
      )}
    </div>
  )
}
