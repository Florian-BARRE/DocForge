// ====== Code Summary ======
// Modal primitive — centered overlay dialog.
// Renders a backdrop and a centered surface-raised card.
// All colors from CSS vars (token-driven). Uses z-index.modal (201).

import { ReactNode, useEffect } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

interface ModalProps {
  /** Whether the modal is visible. */
  isOpen: boolean
  /** Modal title shown in the header. */
  title: ReactNode
  /** Body content. */
  children: ReactNode
  /** Optional footer content (action buttons, etc.). */
  footer?: ReactNode
  /** Called when the backdrop or ESC key is pressed. */
  onClose: () => void
  /** Maximum width of the dialog card in px. Defaults to 480. */
  maxWidth?: number
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Centered overlay dialog.
 *
 * Renders a full-viewport backdrop and a centered card.
 * Pressing ESC closes the modal. All colors are token-driven via CSS vars.
 *
 * Args:
 *   isOpen: Controls visibility.
 *   title: Header title.
 *   children: Dialog body.
 *   footer: Optional footer with action buttons.
 *   onClose: Close callback (ESC or backdrop click).
 *   maxWidth: Card max-width in px.
 */
export function Modal({ isOpen, title, children, footer, onClose, maxWidth = 480 }: ModalProps) {
  // 1. Close on ESC key press.
  useEffect(() => {
    if (!isOpen) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
    >
      {/* Card — stop propagation so clicking inside doesn't close */}
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--surface-raised)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          boxShadow: 'var(--shadow-2)',
          width: '100%',
          maxWidth,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          maxHeight: '85vh',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 16px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{title}</span>
          <button
            type="button"
            className="slide-panel-close"
            onClick={onClose}
            title="Close"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div style={{
            padding: '12px 16px',
            borderTop: '1px solid var(--border)',
            flexShrink: 0,
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 8,
          }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
