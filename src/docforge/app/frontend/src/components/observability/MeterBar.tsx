// ====== Code Summary ======
// MeterBar — small horizontal percentage bar for CPU, RAM, and GPU metrics.
// Used in WorkersPanel. All colors from CSS vars (token-driven).

// ── Types ────────────────────────────────────────────────────────────────────

interface MeterBarProps {
  /** Current value. If max is omitted, treated as a 0-100 percentage. */
  value: number
  /** Maximum value. Defaults to 100. */
  max?: number
  /** Bar fill color (CSS value or var). Drives the colored segment. */
  color?: string
  /** Container width (px or CSS string). Defaults to 72. */
  width?: number | string
  /** Bar height in px. Defaults to 5. */
  height?: number
  /** Tooltip text shown on hover. Falls back to "X%" if omitted. */
  label?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Horizontal percentage meter bar.
 *
 * Shows a filled segment proportional to `value / max`, with a right-aligned
 * percentage label.  Used in WorkersPanel for CPU, RAM, and GPU gauges.
 *
 * Args:
 *   value:  Current value (0 to max).
 *   max:    Maximum value for scale. Defaults to 100.
 *   color:  Fill color as a CSS value (e.g. 'var(--s-done)'). Defaults to accent.
 *   width:  Container width. Defaults to 72px.
 *   height: Bar height in pixels. Defaults to 5.
 *   label:  Hover tooltip. Falls back to formatted percentage.
 */
export function MeterBar({
  value,
  max = 100,
  color = 'var(--accent)',
  width = 72,
  height = 5,
  label,
}: MeterBarProps) {
  const pct      = Math.min(100, Math.max(0, max > 0 ? (value / max) * 100 : 0))
  const tooltip  = label ?? `${pct.toFixed(1)}%`
  const numLabel = max === 100 ? `${value.toFixed(0)}%` : `${value}/${max}`

  return (
    <div
      title={tooltip}
      style={{ display: 'flex', alignItems: 'center', gap: 5 }}
    >
      {/* Track */}
      <div style={{
        width,
        height,
        background: 'var(--surface-raised)',
        borderRadius: height,
        overflow: 'hidden',
        flexShrink: 0,
        border: '1px solid var(--border)',
      }}>
        {/* Fill */}
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: height,
          transition: 'width 0.3s ease',
        }} />
      </div>

      {/* Numeric label */}
      <span style={{
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)',
        flexShrink: 0,
        minWidth: 28,
      }}>
        {numLabel}
      </span>
    </div>
  )
}
