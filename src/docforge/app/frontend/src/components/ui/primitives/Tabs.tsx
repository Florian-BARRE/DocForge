// ====== Code Summary ======
// Tabs primitive — horizontal tab bar with controlled active state.
// Used for doc-detail tabs, admin sub-tabs, chunk browser tabs, etc.
// Supports two display modes: 'underline' (bottom border) and 'pill' (filled bg).

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export interface Tab<T extends string = string> {
  /** Unique key identifying this tab. */
  key: T
  /** Visible label (string or node). */
  label: ReactNode
}

interface TabsProps<T extends string = string> {
  tabs: Tab<T>[]
  active: T
  onChange: (key: T) => void
  /** Visual mode. 'underline' for headers, 'pill' for inline segments. */
  mode?: 'underline' | 'pill'
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Horizontal tab navigation bar.
 *
 * Renders a row of tab buttons with a controlled active state.
 * All colors are from CSS vars (token-driven).
 *
 * Args:
 *   tabs: Array of {key, label} definitions.
 *   active: Currently active tab key.
 *   onChange: Called with the new key when a tab is clicked.
 *   mode: 'underline' shows a bottom accent border; 'pill' fills the background.
 */
export function Tabs<T extends string>({ tabs, active, onChange, mode = 'underline', className = '' }: TabsProps<T>) {
  if (mode === 'pill') {
    return (
      <div className={`app-tabs ${className}`.trim()}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            className={`app-tab${active === tab.key ? ' app-tab-active' : ''}`}
            onClick={() => onChange(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    )
  }

  // Underline mode — matches .doc-detail-tab style
  return (
    <div
      className={className}
      style={{ display: 'flex', borderBottom: '1px solid var(--border)' }}
    >
      {tabs.map(tab => {
        const isActive = active === tab.key
        return (
          <button
            key={tab.key}
            type="button"
            style={{
              padding: '6px 14px',
              fontSize: 12,
              color: isActive ? 'var(--text)' : 'var(--text-muted)',
              borderBottom: `2px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
              marginBottom: -1,
              cursor: 'pointer',
              background: 'transparent',
              border: 'none',
              borderBottomWidth: 2,
              borderBottomStyle: 'solid',
              borderBottomColor: isActive ? 'var(--accent)' : 'transparent',
              transition: 'color 0.15s',
              whiteSpace: 'nowrap',
            }}
            onClick={() => onChange(tab.key)}
          >
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}
