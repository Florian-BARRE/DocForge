// ====== Code Summary ======
// ChainPicker — ordered list builder for kind="chain" ConfigNode entries.
// Uses a `renderChildren` render-prop (injected by RecursiveFieldRenderer) to render
// each entry's params, breaking the circular import cleanly.
// Renamed from MultiPicker (which serves the legacy flat DynamicField path).

// ====== Standard Library Imports ======
import { useState } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode, ProviderChoice } from '../../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** A single chain entry in the wire format: { id, ...params }. */
interface ChainEntry {
  id: string
  [param: string]: unknown
}

/**
 * Render-prop type injected by RecursiveFieldRenderer.
 * Renders a list of ConfigNode children using caller-provided read/write accessors.
 */
export type RenderChildrenFn = (
  nodes: ConfigNode[],
  readValue: (absPath: string) => unknown,
  writeValue: (absPath: string, v: unknown) => void,
) => ReactNode

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build default param values from a ProviderChoice params list.
 *
 * Args:
 *   params: Child ConfigNode list from a ProviderChoice.
 *
 * Returns:
 *   Record<string, unknown>: last-path-segment -> default for non-null defaults.
 */
function paramsDefaults(params: ConfigNode[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const p of params) {
    if (p.default !== null && p.default !== undefined) {
      const seg = p.path.split('.').pop() ?? p.path
      out[seg] = p.default
    }
  }
  return out
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Ordered chain builder for a chain ConfigNode (multi-provider).
 *
 * Renders an ordered list of selected providers. Expanding a chain entry shows
 * its params via the injected `renderChildren` function — handles nested unions
 * uniformly. Entries can be added (by clicking chips) or removed (X button).
 *
 * Args:
 *   node:           The chain ConfigNode describing available providers.
 *   value:          Current ordered list of { id, ...params } entries.
 *   onChange:       Emit the updated chain.
 *   renderChildren: Injected recursive renderer for child param nodes.
 */
export function ChainPicker({
  node,
  value,
  onChange,
  renderChildren,
}: {
  node: ConfigNode
  value: ChainEntry[] | undefined
  onChange: (v: ChainEntry[]) => void
  renderChildren: RenderChildrenFn
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const chain = value ?? []
  const choices = node.choices ?? []

  // 1. Add a new entry at the end of the chain.
  function add(c: ProviderChoice) {
    if (!c.selectable) return
    onChange([...chain, { id: c.id, ...paramsDefaults(c.params ?? []) }])
  }

  // 2. Remove an entry by index.
  function remove(idx: number) {
    onChange(chain.filter((_, i) => i !== idx))
  }

  // 3. Write a param change for one chain entry.
  //    absPath uses the last segment as the flat key (wire format).
  function writeEntryParam(idx: number, absPath: string, v: unknown) {
    const seg = absPath.split('.').pop() ?? absPath
    onChange(
      chain.map((item, i) =>
        i === idx ? { ...item, [seg]: v } : item,
      ),
    )
  }

  const available = choices.filter(c => c.available && c.selectable)
  const displayLabel = node.label || (node.path.split('.').pop() ?? node.path)

  return (
    <div className="picker">
      <div className="picker-label">{displayLabel}</div>

      {/* Ordered list of chain entries */}
      {chain.length > 0 && (
        <div className="chain-list">
          {chain.map((item, idx) => {
            const choice = choices.find(c => c.id === item.id)
            const isOpen = expanded === String(idx)
            const hasParams = (choice?.params ?? []).length > 0

            return (
              <div key={idx} className="chain-item">
                <div className="chain-item-row">
                  <span className="chain-rank mono">{idx + 1}</span>
                  <span className="chain-id">{choice?.label || item.id}</span>
                  {hasParams && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: '2px 6px' }}
                      onClick={() => setExpanded(isOpen ? null : String(idx))}
                      type="button"
                    >
                      {isOpen ? '▲' : '▼'} params
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-danger"
                    onClick={() => remove(idx)}
                    type="button"
                  >
                    ✕
                  </button>
                </div>

                {/* Expanded params via injected recursive renderer */}
                {isOpen && choice && hasParams && (
                  <div className="picker-params fadein" style={{ marginLeft: 28 }}>
                    {renderChildren(
                      choice.params ?? [],
                      // read: last segment from flat entry object
                      (absPath) => {
                        const seg = absPath.split('.').pop() ?? absPath
                        return (item as Record<string, unknown>)[seg]
                      },
                      // write: update the chain entry at this index
                      (absPath, v) => writeEntryParam(idx, absPath, v),
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Add chips */}
      {available.length > 0 && (
        <div className="picker-chips" style={{ marginTop: 8 }}>
          <span className="text-muted" style={{ fontSize: 11 }}>+ add</span>
          {available.map(c => (
            <button
              key={c.id}
              className="chip"
              onClick={() => add(c)}
              type="button"
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
