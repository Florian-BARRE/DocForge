// ====== Code Summary ======
// Select primitive — native <select> with cockpit styling.
// Uses .input and .select CSS classes from global.css (token-driven).

import { SelectHTMLAttributes } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Native dropdown select with cockpit styling.
 *
 * Applies `.input .select` from global.css which sets appearance:none,
 * a chevron background, and reads all colors from CSS vars.
 *
 * Args:
 *   className: Additional CSS classes merged after .input .select.
 */
export function Select({ className = '', ...rest }: SelectProps) {
  return (
    <select
      className={`input select ${className}`.trim()}
      {...rest}
    />
  )
}
