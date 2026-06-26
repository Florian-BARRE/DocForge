// ====== Code Summary ======
// Tag / Badge primitive — inline label for status, metadata, and categories.
// Maps to the .tag CSS class family from global.css (token-driven).
// Status variants use --s-*-soft token backgrounds for a polished, tinted look.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

/** Added 'info' variant for informational (blue) status labels. */
export type TagVariant = 'default' | 'done' | 'running' | 'error' | 'warning' | 'info' | 'accent'

interface TagProps {
  children: ReactNode
  variant?: TagVariant
  className?: string
  style?: React.CSSProperties
}

// ── Helpers ──────────────────────────────────────────────────────────────────

// CSS classes encode the status-soft token pattern (all defined in global.css).
// No hardcoded hex here — global.css owns the soft-bg + tinted-text formula.
const variantClass: Record<TagVariant, string> = {
  default: 'tag',
  done:    'tag tag-done',
  running: 'tag tag-running',
  error:   'tag tag-error',
  warning: 'tag tag-warning',
  info:    'tag tag-info',
  accent:  'tag',
}

// Accent uses inline style (no dedicated CSS class); all others defer to CSS.
const variantStyle: Record<TagVariant, React.CSSProperties> = {
  default: {},
  done:    {},
  running: {},
  error:   {},
  warning: {},
  info:    {},
  accent: {
    background: 'var(--accent-soft)',
    borderColor: 'rgba(99, 102, 241, 0.30)',
    color: 'var(--accent)',
  },
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Inline status or category label.
 *
 * Uses .tag CSS class family from global.css (all colors token-driven).
 * Status variants use --s-*-soft backgrounds with matching tinted text.
 *
 * Args:
 *   variant: Semantic color variant. done=mint, running/warning=amber,
 *            error=coral, info=blue, accent=indigo, default=neutral surface.
 */
export function Tag({ children, variant = 'default', className = '', style }: TagProps) {
  return (
    <span
      className={`${variantClass[variant]} ${className}`.trim()}
      style={{ ...variantStyle[variant], ...style }}
    >
      {children}
    </span>
  )
}
