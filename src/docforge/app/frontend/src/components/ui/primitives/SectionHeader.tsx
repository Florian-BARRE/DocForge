// ====== Code Summary ======
// SectionHeader primitive — uppercase dim label, optionally with a right-side
// action slot. Used to title config groups, inspector sections, data blocks.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface SectionHeaderProps {
  /** Section label text (will be uppercased). */
  children: ReactNode
  /** Optional element rendered on the right side (e.g. an action button). */
  action?: ReactNode
  /** Bottom margin in px. Defaults to 8. */
  gap?: number
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Dense section label with optional trailing action.
 *
 * Renders as an uppercase, letter-spaced, dimmed text row. Matches the
 * `.section-title` visual style from global.css (all colors token-driven).
 *
 * Args:
 *   children: Label text.
 *   action: Optional trailing node (button, badge, etc.).
 *   gap: Margin below the header in pixels.
 */
export function SectionHeader({ children, action, gap = 8 }: SectionHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: gap,
      }}
    >
      <span className="section-title" style={{ marginBottom: 0 }}>
        {children}
      </span>
      {action && <span>{action}</span>}
    </div>
  )
}
