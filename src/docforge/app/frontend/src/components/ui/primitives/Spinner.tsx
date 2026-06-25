// ====== Code Summary ======
// Spinner primitive — inline loading indicator using the .spin CSS animation.
// Uses the existing keyframe from global.css. Color from CSS vars.

// ── Types ────────────────────────────────────────────────────────────────────

interface SpinnerProps {
  /** Diameter in px. Defaults to 14 (dense cockpit default). */
  size?: number
  /** Color override. Defaults to var(--text-muted). */
  color?: string
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Circular loading spinner.
 *
 * Renders a thin bordered circle with a transparent top segment,
 * animated with the `.spin` keyframe from global.css.
 * All default colors come from CSS vars (token-driven).
 *
 * Args:
 *   size: Circle diameter in px.
 *   color: Border color. Defaults to var(--text-muted).
 */
export function Spinner({ size = 14, color = 'var(--text-muted)', className = '' }: SpinnerProps) {
  return (
    <span
      className={`spin ${className}`.trim()}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        border: `2px solid ${color}`,
        borderTopColor: 'transparent',
        flexShrink: 0,
      }}
      aria-label="Loading"
      role="status"
    />
  )
}
