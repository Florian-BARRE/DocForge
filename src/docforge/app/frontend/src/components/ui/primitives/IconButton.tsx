// ====== Code Summary ======
// IconButton primitive — compact square button for icon-only actions.
// Uses .btn-icon CSS class from global.css (token-driven).
// Supports danger variant for destructive actions.

import { ButtonHTMLAttributes, ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Icon or symbol to render inside the button. */
  children: ReactNode
  /** If true, applies danger (red) hover style. */
  danger?: boolean
  /** Accessible label — required for screen readers. */
  title: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Compact icon-only button for toolbar actions.
 *
 * Renders as a square pill using `.btn-icon` from global.css.
 * Danger variant adds red hover via `.btn-icon-danger`.
 *
 * Args:
 *   children: Icon/symbol content.
 *   danger: Enable red hover state for destructive actions.
 *   title: Accessible tooltip text (required).
 */
export function IconButton({ children, danger = false, className = '', ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      className={`btn-icon${danger ? ' btn-icon-danger' : ''} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  )
}
