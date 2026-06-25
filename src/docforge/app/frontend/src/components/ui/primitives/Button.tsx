// ====== Code Summary ======
// Button primitive — token-driven, variant + size props.
// Variants: primary, ghost, danger, subtle.
// Sizes: sm (default-dense), md, lg.
// All colors come from CSS vars (theme.ts → global.css). No hardcoded values.

import { ButtonHTMLAttributes, ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export type ButtonVariant = 'primary' | 'ghost' | 'danger' | 'subtle'
export type ButtonSize    = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style variant. Default: 'subtle'. */
  variant?: ButtonVariant
  /** Size tier. Default: 'sm' (dense cockpit default). */
  size?: ButtonSize
  /** Icon or content to render before the label. */
  icon?: ReactNode
  /** Full-width block button. */
  block?: boolean
  children: ReactNode
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const variantClass: Record<ButtonVariant, string> = {
  primary: 'btn btn-primary',
  ghost:   'btn btn-ghost',
  danger:  'btn btn-danger',
  subtle:  'btn',
}

const sizeStyle: Record<ButtonSize, React.CSSProperties> = {
  sm: { padding: '4px 10px', fontSize: 12, gap: 5 },
  md: { padding: '6px 14px', fontSize: 13, gap: 6 },
  lg: { padding: '8px 18px', fontSize: 14, gap: 8 },
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Primary clickable action primitive.
 *
 * Uses `.btn` CSS class family from global.css (token-driven).
 * Extend via `className` and `style` props.
 *
 * Args:
 *   variant: Visual style. primary=accent fill, ghost=transparent,
 *            danger=red-hover, subtle=surface-raised.
 *   size: sm|md|lg density tier.
 *   icon: Optional leading icon node.
 *   block: If true, renders as a full-width block element.
 */
export function Button({
  variant = 'subtle',
  size = 'sm',
  icon,
  block = false,
  className = '',
  style,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      className={`${variantClass[variant]}${block ? ' btn-block' : ''} ${className}`.trim()}
      style={{ ...sizeStyle[size], width: block ? '100%' : undefined, ...style }}
      {...rest}
    >
      {icon && <span className="btn-icon-slot">{icon}</span>}
      {children}
    </button>
  )
}
