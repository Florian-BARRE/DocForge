// ====== Code Summary ======
// NumberInput primitive — compact numeric input with optional min/max/step.
// Used for pipeline parameter fields (top-k, batch sizes, thresholds, etc.).

import { InputHTMLAttributes } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface NumberInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  /** Width in pixels. Defaults to 72px (dense cockpit default). */
  width?: number
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Dense numeric input for parameter fields.
 *
 * Forces type="number". Width defaults to 72px for a compact cockpit look.
 * All border/color values come from the `.input` CSS class (token-driven).
 *
 * Args:
 *   width: Override the default 72px width.
 */
export function NumberInput({ width = 72, className = '', style, ...rest }: NumberInputProps) {
  return (
    <input
      type="number"
      className={`input ${className}`.trim()}
      style={{ width, textAlign: 'center', paddingLeft: 6, paddingRight: 4, ...style }}
      {...rest}
    />
  )
}
