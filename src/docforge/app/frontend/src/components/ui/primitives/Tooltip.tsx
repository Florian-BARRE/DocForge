// ====== Code Summary ======
// Tooltip primitive — lightweight CSS-only tooltip via title attribute delegation.
// For complex rich tooltips a portal-based approach would be needed;
// this primitive wraps a trigger and delegates to native title for now.

import { ReactNode, HTMLAttributes } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface TooltipProps extends HTMLAttributes<HTMLSpanElement> {
  /** Tooltip text displayed on hover. */
  text: string
  children: ReactNode
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Simple tooltip wrapper using native title attribute.
 *
 * Renders a span that passes `text` as the native `title` attribute.
 * For richer tooltips (portals, custom styling) this primitive should be
 * extended with a floating-UI or CSS-custom-property approach.
 *
 * Args:
 *   text: Tooltip content text.
 *   children: The trigger element(s).
 */
export function Tooltip({ text, children, style, ...rest }: TooltipProps) {
  return (
    <span
      title={text}
      style={{ cursor: 'default', display: 'inline-flex', alignItems: 'center', ...style }}
      {...rest}
    >
      {children}
    </span>
  )
}
