// ====== Code Summary ======
// Skeleton primitive — shimmer placeholder for loading content.
// Uses the .shimmer CSS animation and CSS vars for colors.

// ── Types ────────────────────────────────────────────────────────────────────

interface SkeletonProps {
  /** Width (CSS string or px number). Defaults to '100%'. */
  width?: number | string
  /** Height in px. Defaults to 12. */
  height?: number
  /** Border radius in px. Defaults to 4 (var(--radius-sm)). */
  radius?: number
  className?: string
  style?: React.CSSProperties
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Shimmer loading placeholder.
 *
 * Uses the `.shimmer` CSS animation from global.css (token-driven colors).
 * Render multiple stacked Skeletons to simulate a loading list or card.
 *
 * Args:
 *   width: Element width. Defaults to '100%'.
 *   height: Element height in px.
 *   radius: Border radius in px.
 */
export function Skeleton({ width = '100%', height = 12, radius = 4, className = '', style }: SkeletonProps) {
  return (
    <span
      className={`shimmer ${className}`.trim()}
      style={{
        display: 'inline-block',
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
    />
  )
}
