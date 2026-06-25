// ====== Code Summary ======
// Input primitive — single-line text input, token-driven via .input CSS class.
// Extends the native <input> element, forwarding all HTML attributes.

import { InputHTMLAttributes } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** Extra CSS class names. The .input class is always applied. */
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Single-line text input.
 *
 * Applies the `.input` CSS class from global.css which reads all colors
 * from CSS vars (token-driven). Pass `className` to add additional classes.
 *
 * Args:
 *   className: Additional CSS classes merged after .input.
 */
export function Input({ className = '', ...rest }: InputProps) {
  return (
    <input
      className={`input ${className}`.trim()}
      {...rest}
    />
  )
}
