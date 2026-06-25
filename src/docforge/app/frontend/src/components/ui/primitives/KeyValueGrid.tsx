// ====== Code Summary ======
// KeyValueGrid primitive — dense two-column label/value grid.
// Used in stage trace panels, overview cards, metadata displays.
// Maps to the .kv-grid / .kv-row CSS classes from global.css.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export interface KVEntry {
  /** Left-column label. */
  key: ReactNode
  /** Right-column value. */
  value: ReactNode
}

interface KeyValueGridProps {
  /** Array of key/value pairs to render. */
  entries: KVEntry[]
  /** Left column width in px. Defaults to 160. */
  keyWidth?: number
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Dense two-column key/value display grid.
 *
 * Uses `.kv-grid` and `.kv-row` CSS classes from global.css (token-driven).
 * Keys are rendered in muted color; values in default text color.
 *
 * Args:
 *   entries: Array of {key, value} pairs.
 *   keyWidth: Fixed left column width in px.
 */
export function KeyValueGrid({ entries, keyWidth = 160, className = '' }: KeyValueGridProps) {
  return (
    <div
      className={`kv-grid ${className}`.trim()}
      style={{ gridTemplateColumns: `${keyWidth}px 1fr` }}
    >
      {entries.map((entry, i) => (
        <div key={i} className="kv-row">
          <span className="kv-k">{entry.key}</span>
          <span className="kv-v">{entry.value}</span>
        </div>
      ))}
    </div>
  )
}
