// ====== Code Summary ======
// Panel / Card primitive — a bordered surface container.
// Wraps content in a surface-raised background with standard border/radius.
// All visual values come from CSS vars (token-driven).

import { HTMLAttributes, ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  /** Padding preset. 'none' = no padding, 'sm' = 8px, 'md' = 14px, 'lg' = 20px. */
  padding?: 'none' | 'sm' | 'md' | 'lg'
  /** If true, renders with a stronger accent-colored border. */
  accent?: boolean
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const paddingMap = { none: 0, sm: 8, md: 14, lg: 20 }

// ── Component ────────────────────────────────────────────────────────────────

/**
 * General-purpose surface container.
 *
 * Provides a panel-bg background, standard border (or accent border),
 * and configurable padding. All colors are from CSS vars (token-driven).
 *
 * Args:
 *   padding: Internal padding preset (none/sm/md/lg).
 *   accent: Render with accent-colored border for highlighted panels.
 */
export function Panel({ children, padding = 'md', accent = false, className = '', style, ...rest }: PanelProps) {
  return (
    <div
      className={`${className}`.trim()}
      style={{
        background: 'var(--panel-bg)',
        border: `1px solid ${accent ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        padding: paddingMap[padding],
        // Elevation shadow makes panels read as raised instead of merely outlined.
        boxShadow: accent ? 'var(--shadow-md)' : 'var(--shadow-sm)',
        ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  )
}
