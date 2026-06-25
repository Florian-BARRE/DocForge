// ====== Code Summary ======
// Drawer / SidePanel primitive — right-edge slide-in panel.
// This is a thin wrapper around the existing SlidePanel CSS classes
// (.slide-panel, .slide-panel-open, .slide-panel-overlay) from global.css.
// Composed from token-driven CSS vars. Replaces direct use of SlidePanel
// for new code — keeps the old SlidePanel component alive for existing usage.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface DrawerProps {
  /** Whether the drawer is open. */
  isOpen: boolean
  /** Drawer header title. */
  title: ReactNode
  /** Optional actions row rendered in the header (e.g. extra buttons). */
  headerActions?: ReactNode
  /** Main body content. */
  children: ReactNode
  /** Optional sticky footer content. */
  footer?: ReactNode
  /** Called when the overlay or close button is clicked. */
  onClose: () => void
  /** Panel width in px. Defaults to 380. */
  width?: number
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Right-edge slide-in panel (inspector / form drawer).
 *
 * Uses the `.slide-panel` CSS class family from global.css (all colors
 * from CSS vars). Renders an overlay backdrop and a close button.
 *
 * Args:
 *   isOpen: Controls visibility.
 *   title: Header title content.
 *   headerActions: Optional right-side header controls.
 *   children: Scrollable body content.
 *   footer: Sticky footer content.
 *   onClose: Close callback.
 *   width: Panel width override in px.
 */
export function Drawer({ isOpen, title, headerActions, children, footer, onClose, width = 380 }: DrawerProps) {
  return (
    <>
      {/* ── Dimming overlay ── */}
      <div
        className={`slide-panel-overlay${isOpen ? ' slide-panel-overlay-open' : ''}`}
        onClick={onClose}
      />

      {/* ── Panel ── */}
      <div
        className={`slide-panel${isOpen ? ' slide-panel-open' : ''}`}
        style={{ width }}
      >
        {/* Header */}
        <div className="slide-panel-header">
          <span className="slide-panel-title">{title}</span>
          {headerActions}
          <button
            type="button"
            className="slide-panel-close"
            onClick={onClose}
            title="Close"
            aria-label="Close panel"
          >
            &times;
          </button>
        </div>

        {/* Scrollable body */}
        <div className="slide-panel-body">
          {children}
        </div>

        {/* Optional footer */}
        {footer && (
          <div className="slide-panel-footer">
            {footer}
          </div>
        )}
      </div>
    </>
  )
}
