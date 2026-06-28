// ====== Code Summary ======
// ValueRenderer — generic recursive renderer for any unknown metadata value.
// Classifies the value by type and structure, then renders it appropriately.
// Never produces "[object Object]" or raw array comma-joins.
// Dark-first; all styling via CSS custom-property tokens (no hardcoded colors).

import { useState } from 'react'

// ── Detectors ─────────────────────────────────────────────────────────────────

/** Matches blake3 / sha256 / md5 hex digests (32+ lowercase hex chars, no separators). */
const HEX_RE   = /^[0-9a-f]{32,}$/i

/** Matches ISO 8601 datetime strings produced by Python's datetime.isoformat(). */
const ISO_RE   = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

/** SeaweedFS / S3 content-addressed object-key prefixes. */
const PATH_PFXS = ['derived/', 'originals/', 'pages/', 'chunks/']

const isHex  = (s: string) => HEX_RE.test(s)
const isIso  = (s: string) => ISO_RE.test(s)
const isPath = (s: string) => PATH_PFXS.some(p => s.startsWith(p))

/** True when a value does not need recursive rendering (null / scalar). */
const isPrim = (v: unknown): boolean => v === null || typeof v !== 'object'

// ── Sub-components ────────────────────────────────────────────────────────────

/**
 * Truncated hex hash with an inline clipboard-copy button.
 *
 * Displays the first 7 and last 7 characters. Hovering over the text shows
 * the full hash via title attribute. The ⎘ button copies the full hash and
 * briefly shows a ✓ confirmation.
 *
 * Args:
 *   full: The complete hex string.
 */
function HashValue({ full }: { full: string }) {
  const [copied, setCopied] = useState(false)
  const short = `${full.slice(0, 7)}…${full.slice(-7)}`

  function copy() {
    navigator.clipboard.writeText(full).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    })
  }

  return (
    <span className="vr-hash">
      <span className="vr-hash-text mono" title={full}>{short}</span>
      <button type="button" className="vr-copy-btn" onClick={copy} title="Copy full value">
        {copied ? '✓' : '⎘'}
      </button>
    </span>
  )
}

/**
 * Array containing at least one object: shows a count chip that expands
 * to reveal individual items, each recursively rendered by ValueRenderer.
 *
 * Args:
 *   items: The array of values (mix of objects and/or primitives).
 */
function ArrayObjectValue({ items }: { items: unknown[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button type="button" className="vr-count-chip" onClick={() => setOpen(o => !o)}>
        {open ? '▲' : '▼'} {items.length} item{items.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <div className="vr-expand-list">
          {items.map((item, i) => (
            <div key={i} className="vr-expand-item">
              <span className="text-dim" style={{ fontSize: 9, marginRight: 5 }}>[{i}]</span>
              <ValueRenderer value={item} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Plain object: shows a field-count chip that expands to a compact KV block.
 * Each value is recursively rendered by ValueRenderer.
 *
 * Args:
 *   obj: The plain object to render.
 */
function ObjectValue({ obj }: { obj: Record<string, unknown> }) {
  const [open, setOpen] = useState(false)
  const keys = Object.keys(obj)
  if (keys.length === 0) {
    return <span className="text-dim" style={{ fontSize: 11 }}>{'{}'}</span>
  }
  return (
    <div>
      <button type="button" className="vr-count-chip" onClick={() => setOpen(o => !o)}>
        {open ? '▲' : '▼'} {keys.length} field{keys.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <div className="vr-obj-block">
          {keys.map(k => (
            <div key={k} style={{ display: 'contents' }}>
              <span className="vr-obj-k">{k}</span>
              <span className="vr-obj-v"><ValueRenderer value={obj[k]} /></span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main dispatcher ───────────────────────────────────────────────────────────

interface ValueRendererProps {
  /** The value to classify and render. May be any type, including unknown. */
  value: unknown
}

/**
 * Generic recursive value renderer for document metadata.
 *
 * Classification hierarchy (evaluated in order):
 *   1.  null / undefined / ""    → muted dash
 *   2.  boolean                  → "✓ yes" (green) / "✗ no" (muted) badge
 *   3.  ISO 8601 string          → formatted date/time via toLocaleString
 *   4.  hex hash string (≥32 ch) → truncated mono + clipboard copy button
 *   5.  storage-path string      → basename with full path as title
 *   6.  number                   → locale-formatted (toLocaleString)
 *   7.  array (all primitives)   → comma-joined string
 *   8.  array (has objects)      → count chip + collapsible list
 *   9.  plain object             → field-count chip + collapsible KV block
 *  10.  other string             → plain text at 11px
 *  11.  fallback                 → String(v)
 *
 * Args:
 *   value: Any value to classify and render.
 */
export function ValueRenderer({ value }: ValueRendererProps) {
  // 1. Null / empty
  if (value === null || value === undefined || value === '') {
    return <span className="text-dim" style={{ fontSize: 11 }}>—</span>
  }

  // 2. Boolean — badge style avoids the literal word "true" / "false"
  if (typeof value === 'boolean') {
    return value
      ? <span className="tag vr-bool-true">&#10003; yes</span>
      : <span className="tag vr-bool-false">&#10005; no</span>
  }

  // 3–5. String detections (order matters: ISO before hex before path)
  if (typeof value === 'string') {
    if (isIso(value))  return <span style={{ fontSize: 11 }}>{new Date(value).toLocaleString()}</span>
    if (isHex(value))  return <HashValue full={value} />
    if (isPath(value)) {
      const name = value.split('/').pop() ?? value
      return <span className="mono text-dim" style={{ fontSize: 11 }} title={value}>{name}</span>
    }
    return <span style={{ fontSize: 11 }}>{value}</span>
  }

  // 6. Number
  if (typeof value === 'number') {
    return <span style={{ fontSize: 11 }}>{value.toLocaleString()}</span>
  }

  // 7–8. Array
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-dim" style={{ fontSize: 11 }}>—</span>
    if (value.every(isPrim)) return <span style={{ fontSize: 11 }}>{value.map(String).join(', ')}</span>
    return <ArrayObjectValue items={value} />
  }

  // 9. Plain object
  if (typeof value === 'object') {
    return <ObjectValue obj={value as Record<string, unknown>} />
  }

  // 11. Fallback — should never produce "[object Object]" since arrays/objects are handled above
  return <span style={{ fontSize: 11 }}>{String(value)}</span>
}
