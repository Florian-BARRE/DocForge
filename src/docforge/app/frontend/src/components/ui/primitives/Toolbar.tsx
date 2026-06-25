// ====== Code Summary ======
// Toolbar primitive — horizontal strip of controls with consistent spacing.
// Used as the action row at the top of document lists, search panes, etc.
// All colors from CSS vars (token-driven).

import { HTMLAttributes, ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface ToolbarProps extends HTMLAttributes<HTMLDivElement> {
  /** Left-side controls. */
  left?: ReactNode
  /** Right-side controls. */
  right?: ReactNode
  /** Padding preset: 'none' | 'sm' | 'md'. Defaults to 'sm'. */
  padding?: 'none' | 'sm' | 'md'
  /** Show bottom border. Defaults to false. */
  border?: boolean
  children?: ReactNode
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const paddingMap = { none: '0', sm: '6px 12px', md: '10px 16px' }

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Horizontal toolbar strip.
 *
 * Renders a flex row with left/right slots (or free children).
 * All colors are from CSS vars (token-driven). Background is var(--surface).
 *
 * Args:
 *   left: Controls anchored to the left.
 *   right: Controls anchored to the right.
 *   padding: Internal padding preset.
 *   border: If true adds a bottom border using var(--border).
 */
export function Toolbar({ left, right, children, padding = 'sm', border = false, className = '', style, ...rest }: ToolbarProps) {
  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: paddingMap[padding],
        background: 'var(--surface)',
        borderBottom: border ? '1px solid var(--border)' : undefined,
        flexShrink: 0,
        flexWrap: 'wrap',
        ...style,
      }}
      {...rest}
    >
      {left && <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{left}</div>}
      {children}
      {right && <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>{right}</div>}
    </div>
  )
}
