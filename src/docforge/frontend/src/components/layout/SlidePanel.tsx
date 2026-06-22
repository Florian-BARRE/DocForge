// ====== Code Summary ======
// Generic slide-in panel from the right edge of the viewport.
// Supports an optional footer slot, overlay-click and Escape-key dismissal,
// and smooth 200 ms enter/exit transitions driven by CSS classes.

// ====== Third-Party Library Imports ======
import { useEffect } from 'react'
import type { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface SlidePanelProps {
  /** Controls whether the panel is visible. */
  isOpen: boolean
  /** Text rendered in the panel header. */
  title: string
  /** Called when the user dismisses the panel (Escape key or overlay click). */
  onClose: () => void
  /** Main panel content rendered in the scrollable body area. */
  children: ReactNode
  /** Optional footer content rendered below the scrollable body. */
  footer?: ReactNode
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * A fixed-position panel that slides in from the right side of the viewport.
 *
 * The panel occupies full viewport height at a fixed 380 px width. When open, a
 * semi-transparent overlay covers the rest of the screen and can be clicked to
 * close the panel. Pressing Escape also closes it.
 *
 * Args:
 *   isOpen:   Whether the panel is currently visible and interactive.
 *   title:    Heading text shown in the sticky panel header.
 *   onClose:  Callback invoked on overlay click or Escape keydown.
 *   children: Scrollable body content.
 *   footer:   Optional sticky footer rendered beneath the body.
 */
export function SlidePanel({ isOpen, title, onClose, children, footer }: SlidePanelProps) {
  // 1. Register Escape key listener — only active while the panel is open.
  useEffect(() => {
    if (!isOpen) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  return (
    <>
      {/* ── Overlay ── */}
      <div
        className={`slide-panel-overlay${isOpen ? ' slide-panel-overlay-open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* ── Panel ── */}
      <div
        className={`slide-panel${isOpen ? ' slide-panel-open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        {/* Header */}
        <div className="slide-panel-header">
          <span className="slide-panel-title">{title}</span>
          <button
            type="button"
            className="slide-panel-close"
            onClick={onClose}
            aria-label="Close panel"
          >
            ×
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
