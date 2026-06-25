// ====== Code Summary ======
// Tag / Badge primitive — inline label for status, metadata, and categories.
// Maps to the .tag CSS class family from global.css (token-driven).
// Supports status variants (done/running/error/warning) and custom color.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export type TagVariant = 'default' | 'done' | 'running' | 'error' | 'warning' | 'accent'

interface TagProps {
  children: ReactNode
  variant?: TagVariant
  className?: string
  style?: React.CSSProperties
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const variantClass: Record<TagVariant, string> = {
  default: 'tag',
  done:    'tag tag-done',
  running: 'tag tag-running',
  error:   'tag tag-error',
  warning: 'tag',
  accent:  'tag',
}

const variantStyle: Record<TagVariant, React.CSSProperties> = {
  default: {},
  done:    {},
  running: {},
  error:   {},
  warning: {
    background: 'color-mix(in srgb, var(--s-warning) 14%, transparent)',
    borderColor: 'color-mix(in srgb, var(--s-warning) 40%, transparent)',
    color: 'var(--s-warning)',
  },
  accent: {
    background: 'var(--accent-soft)',
    borderColor: 'color-mix(in srgb, var(--accent) 40%, transparent)',
    color: 'var(--accent)',
  },
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Inline status or category label.
 *
 * Uses `.tag` CSS class family from global.css (all colors token-driven).
 * Variant maps to semantic color (done=green, running=orange, error=red).
 *
 * Args:
 *   variant: Semantic color variant. Default renders neutral surface.
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
