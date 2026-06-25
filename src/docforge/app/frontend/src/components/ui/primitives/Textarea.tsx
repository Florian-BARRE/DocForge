// ====== Code Summary ======
// Textarea primitive — multi-line text input, token-driven via .input class.
// All colors come from CSS vars. Resizes vertically by default.

import { TextareaHTMLAttributes } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  /** Number of visible rows. Defaults to 3 (dense). */
  rows?: number
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Multi-line text input.
 *
 * Applies `.input` from global.css (all colors from CSS vars).
 * Sets resize to 'vertical' by default for dense forms.
 *
 * Args:
 *   rows: Visible row count. Defaults to 3.
 */
export function Textarea({ rows = 3, className = '', style, ...rest }: TextareaProps) {
  return (
    <textarea
      rows={rows}
      className={`input ${className}`.trim()}
      style={{ resize: 'vertical', ...style }}
      {...rest}
    />
  )
}
