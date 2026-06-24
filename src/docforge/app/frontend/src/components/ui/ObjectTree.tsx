// ====== Code Summary ======
// <ObjectTree> — generic recursive renderer for arbitrary JSON / typed objects.
// Used everywhere the UI needs to display "everything the backend returned" without
// hand-coding a layout: implicit_meta, user_meta, IR samples, raw config snapshots,
// chain trace details, etc.
//
// Visual contract:
//   • Primitives (string / number / boolean / null) → coloured value with type tag.
//   • Arrays / objects → collapsible row with arrow + length / key count badge.
//   • A "secret" mask is applied when the key matches /key|secret|password|token|api/i
//     so a config dump never leaks credentials.
//   • Long strings get truncated with a "more" affordance.
//
// The component is intentionally typed against `unknown` so callers don't have to
// narrow ahead of time — pass any Pydantic-mirrored object and the tree appears.

import { useState } from 'react'

interface Props {
  value: unknown
  // Optional override for the root label (default: none).
  label?: string
  // Optional default expansion (depth-aware).  -1 = collapsed, 0 = open root only,
  // 1 = open one level, … and Infinity = fully expanded.
  defaultDepth?: number
  // Optional collapsed labels for keys whose values are large (e.g. "blocks": …).
  // The renderer never recurses into a key in this set unless the user clicks.
  alwaysCollapsedKeys?: string[]
  // Override the secret-detection regex.  Default matches the backend's masking.
  secretKeyRegex?: RegExp
}

const DEFAULT_SECRET_RX = /key|secret|password|token|api[_-]?key|credential|auth/i

export function ObjectTree({
  value, label, defaultDepth = 1, alwaysCollapsedKeys, secretKeyRegex,
}: Props) {
  return (
    <div className="object-tree" style={{ fontSize: 11 }}>
      <Node
        value={value}
        keyName={label}
        depth={0}
        defaultDepth={defaultDepth}
        alwaysCollapsedKeys={new Set(alwaysCollapsedKeys ?? [])}
        secretRx={secretKeyRegex ?? DEFAULT_SECRET_RX}
      />
    </div>
  )
}

// ── One node ─────────────────────────────────────────────────────────────────

function Node({
  value, keyName, depth, defaultDepth, alwaysCollapsedKeys, secretRx,
}: {
  value: unknown
  keyName?: string
  depth: number
  defaultDepth: number
  alwaysCollapsedKeys: Set<string>
  secretRx: RegExp
}) {
  const initiallyOpen = depth <= defaultDepth && !(keyName && alwaysCollapsedKeys.has(keyName))
  const [open, setOpen] = useState<boolean>(initiallyOpen)

  // ── Primitive leaf ──
  if (value === null) return <Leaf keyName={keyName} type="null" display="null" />
  if (typeof value === 'string') {
    const isSecret = !!keyName && secretRx.test(keyName)
    return (
      <Leaf
        keyName={keyName}
        type="string"
        display={isSecret ? '••• (masked)' : truncate(JSON.stringify(value), 200)}
        valueColor={isSecret ? 'var(--text-dim)' : '#d1bf85'}
      />
    )
  }
  if (typeof value === 'number')  return <Leaf keyName={keyName} type="number"  display={String(value)} valueColor="#9ecbff" />
  if (typeof value === 'boolean') return <Leaf keyName={keyName} type="boolean" display={String(value)} valueColor={value ? '#86efac' : '#fda4af'} />
  if (typeof value === 'undefined') return <Leaf keyName={keyName} type="undefined" display="undefined" />

  // ── Array ──
  if (Array.isArray(value)) {
    return (
      <Composite
        keyName={keyName}
        kind="array"
        summary={`${value.length} item${value.length === 1 ? '' : 's'}`}
        open={open}
        onToggle={() => setOpen(o => !o)}
      >
        {open && value.map((item, i) => (
          <Node
            key={i}
            value={item}
            keyName={String(i)}
            depth={depth + 1}
            defaultDepth={defaultDepth}
            alwaysCollapsedKeys={alwaysCollapsedKeys}
            secretRx={secretRx}
          />
        ))}
      </Composite>
    )
  }

  // ── Object ──
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
    return (
      <Composite
        keyName={keyName}
        kind="object"
        summary={`${entries.length} key${entries.length === 1 ? '' : 's'}`}
        open={open}
        onToggle={() => setOpen(o => !o)}
      >
        {open && entries.map(([k, v]) => (
          <Node
            key={k}
            value={v}
            keyName={k}
            depth={depth + 1}
            defaultDepth={defaultDepth}
            alwaysCollapsedKeys={alwaysCollapsedKeys}
            secretRx={secretRx}
          />
        ))}
      </Composite>
    )
  }

  // ── Unknown / function / symbol ──
  return <Leaf keyName={keyName} type={typeof value} display="(opaque)" />
}

// ── Visual leaves ────────────────────────────────────────────────────────────

function Leaf({
  keyName, type, display, valueColor,
}: {
  keyName?: string
  type: string
  display: string
  valueColor?: string
}) {
  return (
    <div className="object-tree-row">
      {keyName !== undefined && (
        <span className="mono" style={{ color: 'var(--text-muted)' }}>{keyName}:</span>
      )}
      <span
        className="mono"
        style={{
          color: valueColor ?? 'var(--text)',
          maxWidth: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}
      >
        {display}
      </span>
      <TypeBadge type={type} />
    </div>
  )
}

function Composite({
  keyName, kind, summary, open, onToggle, children,
}: {
  keyName?: string
  kind: 'array' | 'object'
  summary: string
  open: boolean
  onToggle: () => void
  children?: React.ReactNode
}) {
  return (
    <div>
      <div className="object-tree-row" style={{ cursor: 'pointer' }} onClick={onToggle}>
        <span style={{ color: 'var(--text-dim)', width: 10, display: 'inline-block' }}>{open ? '▾' : '▸'}</span>
        {keyName !== undefined && (
          <span className="mono" style={{ color: 'var(--text-muted)' }}>{keyName}:</span>
        )}
        <span style={{ color: 'var(--text-dim)' }}>{kind === 'array' ? '[ … ]' : '{ … }'}</span>
        <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{summary}</span>
      </div>
      {open && (
        <div style={{ marginLeft: 14, borderLeft: '1px dashed var(--border)', paddingLeft: 8 }}>
          {children}
        </div>
      )}
    </div>
  )
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span
      style={{
        fontSize: 9, padding: '0 4px', borderRadius: 3,
        background: 'var(--border)', color: 'var(--text-dim)',
        textTransform: 'uppercase', letterSpacing: '0.04em',
      }}
    >
      {type}
    </span>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + '…' : s
}
