// ====== Code Summary ======
// ObjectListPicker — generic repeater for kind="object_list" ConfigNode entries.
//
// Renders the current array of items, add/remove controls, and for each item recurses
// node.item_schema via the renderChildren render-prop with item-local read/write.
//
// Item-local accessor strategy (mirrors ChainLadder.writeEntryParam):
//   The last path segment is extracted from each item_schema node's abs path and used
//   as the key in the flat item object.  This works regardless of whether the backend
//   emits paths like "patch.pipeline.metagen.targets[].field" or "item.field" — the
//   last segment is always the field name.
//
// GENERIC — no hardcoding of "metagen", field names, or scope semantics.  Works for
// any list[model] whose fields can be described by ConfigNode item_schema entries.

// ====== Third-Party Library Imports ======
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode } from '../../../api/types'
import type { RenderChildrenFn } from '../../pipeline/ChainLadder'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ObjectListPickerProps {
  /** The object_list ConfigNode from the discovery config_tree. */
  node: ConfigNode
  /** Current array value (list of flat item objects). May be undefined (treat as empty). */
  value: Record<string, unknown>[] | undefined
  /** Emit the updated array after any mutation (add / remove / field edit). */
  onChange: (v: Record<string, unknown>[]) => void
  /** Injected recursive renderer for item sub-fields (from RecursiveFieldRenderer). */
  renderChildren: RenderChildrenFn
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Humanize a snake_case last-segment into a readable label.
 *
 * Args:
 *   seg: Raw path segment (e.g. "metagen_targets").
 *
 * Returns:
 *   string: Human-readable label (e.g. "Metagen Targets").
 */
function humanize(seg: string): string {
  return seg
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
}

/**
 * Build a blank item pre-filled with schema defaults.
 *
 * Iterates item_schema nodes; any node with a non-null default contributes its
 * last-segment key.  Nodes without a default are omitted (the server will use its
 * own default on save).
 *
 * Args:
 *   schema: ConfigNode[] from node.item_schema.
 *
 * Returns:
 *   Record<string, unknown>: flat object with last-segment keys.
 */
function blankItem(schema: ConfigNode[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const n of schema) {
    if (n.default !== null && n.default !== undefined) {
      out[n.path.split('.').pop() ?? n.path] = n.default
    }
  }
  return out
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Generic list-of-objects repeater driven by ConfigNode item_schema.
 *
 * Renders the current item array with add/remove controls.  Each item expands its
 * schema via the `renderChildren` render-prop so that nested selects, toggles, and
 * text areas are rendered by the same pipeline as any other ConfigNode — no
 * duplicate field-rendering logic.
 *
 * The caller (RecursiveFieldRenderer) provides `renderChildren`; this component never
 * re-implements field rendering itself.  It only manages the array: add row, remove
 * row, route mutations back to the parent draft.
 *
 * Args:
 *   node:           The object_list ConfigNode (label, description, item_schema).
 *   value:          Current item array (undefined treated as empty).
 *   onChange:       Callback with the full updated array after any mutation.
 *   renderChildren: Injected renderer; called once per item with item-local accessors.
 */
export function ObjectListPicker({ node, value, onChange, renderChildren }: ObjectListPickerProps): ReactNode {
  const items = value ?? []
  const itemSchema = node.item_schema ?? []
  const seg = node.path.split('.').pop() ?? node.path
  const label = node.label || humanize(seg)

  // ── Mutation helpers ────────────────────────────────────────────────────────

  /** Append a new blank item pre-filled with schema defaults. */
  function addItem(): void {
    onChange([...items, blankItem(itemSchema)])
  }

  /** Remove the item at the given index, shifting later items down. */
  function removeItem(idx: number): void {
    onChange(items.filter((_, i) => i !== idx))
  }

  // ── Item-local read/write accessors ────────────────────────────────────────
  //
  // RecursiveFieldRenderer provides read/write with absolute node.path keys.
  // For items in a list we don't have absolute paths — the item_schema nodes carry
  // the template path (e.g. "patch.pipeline.metagen.targets[].field").  We reduce
  // any abs path to its last segment, then look up / mutate the flat item object.
  // This matches how ChainLadder handles provider entry params.

  /**
   * Build an item-local read accessor for the given item object.
   *
   * Args:
   *   item: The flat item record.
   *
   * Returns:
   *   Accessor that resolves the last path segment from the item.
   */
  function makeReadEntry(item: Record<string, unknown>): (absPath: string) => unknown {
    return (absPath: string): unknown => {
      const key = absPath.split('.').pop() ?? absPath
      return item[key]
    }
  }

  /**
   * Build an item-local write accessor that emits the complete updated array.
   *
   * Args:
   *   idx:  Index of the item being edited.
   *   item: Current flat item record (closed over for non-mutated fields).
   *
   * Returns:
   *   Write accessor that splices the updated item into the array and calls onChange.
   */
  function makeWriteEntry(
    idx: number,
    item: Record<string, unknown>,
  ): (absPath: string, v: unknown) => void {
    return (absPath: string, v: unknown): void => {
      const key = absPath.split('.').pop() ?? absPath
      const updated = { ...item, [key]: v }
      onChange(items.map((it, i) => (i === idx ? updated : it)))
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="object-list-picker">
      {/* Header: label + description */}
      <div className="object-list-picker-header">
        <span className="object-list-picker-title">{label}</span>
        {node.description && (
          <span className="object-list-picker-hint">{node.description}</span>
        )}
      </div>

      {/* Empty state */}
      {items.length === 0 && (
        <div className="picker-note">No entries yet — use the button below to add one.</div>
      )}

      {/* Item rows */}
      {items.map((item, idx) => (
        <div key={idx} className="object-list-picker-item">
          {/* Item header: index badge + remove button */}
          <div className="object-list-picker-item-header">
            <span className="object-list-picker-item-index">#{idx + 1}</span>
            <button
              type="button"
              className="btn-icon"
              aria-label={`Remove entry #${idx + 1}`}
              title="Remove this entry"
              onClick={() => removeItem(idx)}
            >
              ×
            </button>
          </div>

          {/* Item fields — recurses through the same RecursiveFieldRenderer path */}
          {itemSchema.length > 0 && (
            <div className="object-list-picker-item-fields">
              {renderChildren(
                itemSchema,
                makeReadEntry(item),
                makeWriteEntry(idx, item),
              )}
            </div>
          )}
        </div>
      ))}

      {/* Add entry button */}
      <button
        type="button"
        className="btn btn-ghost"
        style={{ marginTop: 8, fontSize: 12 }}
        onClick={addItem}
      >
        + Add entry
      </button>
    </div>
  )
}
