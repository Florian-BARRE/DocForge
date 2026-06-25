// ====== Code Summary ======
// ProviderUnionPicker — chip group for kind="provider_union" ConfigNode entries.
// Uses a `renderChildren` render-prop (injected by RecursiveFieldRenderer) to render
// each choice's params, breaking the circular import:
//   RecursiveFieldRenderer -> ProviderUnionPicker -(render-prop)-> RecursiveFieldRenderer.
// Replaces the NestedProviderPicker inner function + NESTED_PROVIDER_FIELDS hack.

// ====== Internal Project Imports ======
import type { ReactNode } from 'react'
import type { ConfigNode, ProviderChoice } from '../../../api/types'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Build default param values from a ProviderChoice params list.
 * Only nodes with a non-null default are included.
 *
 * Args:
 *   params: Child ConfigNode list from a ProviderChoice.
 *
 * Returns:
 *   Record<string, unknown>: last-path-segment -> default value map.
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

/**
 * Resolve the active choice ID from current value or first selectable choice.
 *
 * ISSUE-2 fix: "default" is the first available+selectable choice, not the
 * ProviderChoice.default flag (which the backend sets inconsistently).
 *
 * Args:
 *   value:   Current wire object { id, ...params } or null/undefined.
 *   choices: Provider choices list.
 *
 * Returns:
 *   string | undefined: Resolved selected choice ID.
 */
export function resolveSelectedId(
  value: Record<string, unknown> | null | undefined,
  choices: ProviderChoice[],
): string | undefined {
  if (value?.id) return String(value.id)
  return choices.find(c => c.available && c.selectable)?.id
}

// ── Types ─────────────────────────────────────────────────────────────────────

/**
 * Render-prop type injected by RecursiveFieldRenderer.
 * Renders a list of ConfigNode children using caller-provided read/write accessors.
 */
export type RenderChildrenFn = (
  nodes: ConfigNode[],
  readValue: (absPath: string) => unknown,
  writeValue: (absPath: string, v: unknown) => void,
) => ReactNode

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Chip-group picker for a provider_union ConfigNode (single-choice).
 *
 * The selected choice's params are rendered via the injected `renderChildren`
 * function — no direct import of RecursiveFieldRenderer, so no module cycle.
 * When `node.optional` is true a "disabled" chip clears the selection.
 *
 * ISSUE-2: the "default" badge derives from the first available+selectable choice,
 * not ProviderChoice.default (which is a deprecated/inconsistent flag).
 *
 * Args:
 *   node:           The provider_union ConfigNode.
 *   value:          Current wire value: { id, ...params } or null when disabled.
 *   onChange:       Emit the new value on selection or param change.
 *   renderChildren: Injected recursive renderer for child param nodes.
 */
export function ProviderUnionPicker({
  node,
  value,
  onChange,
  renderChildren,
}: {
  node: ConfigNode
  value: Record<string, unknown> | null | undefined
  onChange: (v: Record<string, unknown> | null) => void
  renderChildren: RenderChildrenFn
}) {
  const choices = node.choices ?? []
  const selectedId = resolveSelectedId(value, choices)
  const selectedChoice = choices.find(c => c.id === selectedId)

  // The "default" is the first available+selectable choice (ISSUE-2 fix).
  const defaultId = choices.find(c => c.available && c.selectable)?.id

  // 1. User clicks a chip — emit { id, ...paramDefaults }.
  function selectChoice(c: ProviderChoice) {
    if (!c.selectable) return
    onChange({ id: c.id, ...paramsDefaults(c.params ?? []) })
  }

  // 2. Build read/write accessors for the selected choice's params.
  //    Provider params are stored flat alongside `id` in the wire format.
  //    The absolute param path from the tree uses the last segment as the key.
  const paramValue = (value ?? {}) as Record<string, unknown>

  function readParam(absPath: string): unknown {
    const seg = absPath.split('.').pop() ?? absPath
    return paramValue[seg]
  }

  function writeParam(absPath: string, v: unknown) {
    const seg = absPath.split('.').pop() ?? absPath
    const updated: Record<string, unknown> = {
      ...(value ?? { id: selectedId }),
      [seg]: v,
    }
    onChange(updated)
  }

  const displayLabel = node.label || (node.path.split('.').pop() ?? node.path)

  return (
    <div className="picker">
      <div className="picker-label">{displayLabel}</div>

      <div className="picker-chips">
        {/* Optional "disabled" chip — clears the selection */}
        {node.optional && (
          <button
            className={`chip ${!selectedId ? 'chip-active' : ''}`}
            onClick={() => onChange(null)}
            type="button"
          >
            disabled
          </button>
        )}

        {choices.map(c => (
          <button
            key={c.id}
            className={`chip ${c.id === selectedId ? 'chip-active' : ''} ${!c.available ? 'chip-unavailable' : ''}`}
            onClick={() => selectChoice(c)}
            title={
              c.note
                ? c.note
                : !c.available
                  ? 'Not available in this deployment'
                  : c.id === defaultId
                    ? 'Default selection'
                    : undefined
            }
            type="button"
            disabled={!c.selectable}
          >
            {c.label || c.id}
            {/* Default indicator: small dot when this is the default but not selected */}
            {c.id === defaultId && c.id !== selectedId && (
              <span className="chip-default-dot" />
            )}
            {!c.available && <span className="chip-dot chip-dot-off" />}
          </button>
        ))}
      </div>

      {/* Params of the selected choice rendered by the injected recursive function */}
      {selectedChoice && (selectedChoice.params ?? []).length > 0 && (
        <div className="picker-params fadein">
          {renderChildren(selectedChoice.params ?? [], readParam, writeParam)}
        </div>
      )}

      {selectedChoice?.note && !selectedChoice.available && (
        <div className="picker-note">{selectedChoice.note}</div>
      )}
    </div>
  )
}
