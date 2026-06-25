// ====== Code Summary ======
// StatusDot primitive — small colored circle indicating pipeline/document status.
// Maps to the .dot CSS class from global.css. All colors from CSS vars.

// ── Types ────────────────────────────────────────────────────────────────────

export type DotStatus = 'done' | 'running' | 'error' | 'pending' | 'idle' | 'skip' | 'warning'

interface StatusDotProps {
  status: DotStatus
  /** Override dot size in px. Defaults to 7. */
  size?: number
  title?: string
  className?: string
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const colorMap: Record<DotStatus, string> = {
  done:    'var(--s-done)',
  running: 'var(--s-running)',
  error:   'var(--s-error)',
  pending: 'var(--s-pending)',
  idle:    'var(--s-idle)',
  skip:    'var(--s-idle)',
  warning: 'var(--s-warning)',
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Small status indicator circle.
 *
 * Renders a solid circle whose color maps to the semantic status token.
 * All colors are CSS vars (token-driven).
 *
 * Args:
 *   status: Semantic status key.
 *   size: Circle diameter in px. Defaults to 7.
 *   title: Tooltip text for accessibility.
 */
export function StatusDot({ status, size = 7, title, className = '' }: StatusDotProps) {
  return (
    <span
      className={`dot ${className}`.trim()}
      title={title}
      style={{
        width: size,
        height: size,
        background: colorMap[status],
        flexShrink: 0,
        borderRadius: '50%',
        display: 'inline-block',
      }}
    />
  )
}
