// ====== Code Summary ======
// EmptyState primitive — centered placeholder shown when a list or panel has no data.
// Uses .empty CSS class from global.css (token-driven colors).

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  /** Icon/emoji displayed above the message. */
  icon?: ReactNode
  /** Primary empty-state message. */
  message: ReactNode
  /** Optional secondary description text. */
  description?: ReactNode
  /** Optional action button or link. */
  action?: ReactNode
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Centered empty-state placeholder.
 *
 * Uses `.empty` CSS class from global.css (all colors token-driven).
 * Renders icon, message, optional description, optional action.
 *
 * Args:
 *   icon: Optional leading icon/emoji node.
 *   message: Primary message text.
 *   description: Secondary descriptive text.
 *   action: Optional call-to-action element.
 */
export function EmptyState({ icon, message, description, action }: EmptyStateProps) {
  return (
    <div className="empty">
      {icon && <span className="empty-icon">{icon}</span>}
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{message}</span>
      {description && (
        <span style={{ fontSize: 12, color: 'var(--text-dim)', maxWidth: 320, textAlign: 'center' }}>
          {description}
        </span>
      )}
      {action && <div style={{ marginTop: 8 }}>{action}</div>}
    </div>
  )
}
