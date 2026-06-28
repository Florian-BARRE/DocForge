// ====== Code Summary ======
// ConfirmDialog — reusable styled confirmation dialog built on the Modal primitive.
// Replaces browser-native window.confirm() with a token-driven overlay.
// Keyboard: Enter confirms (button receives autoFocus), Escape cancels (Modal keydown).
// Use danger=true for irreversible destructive actions (delete, revoke, etc.).

import { ReactNode } from 'react'

// ====== Local Project Imports ======
import { Button } from './primitives/Button'
import { Modal } from './primitives/Modal'

// ── Types ────────────────────────────────────────────────────────────────────

interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean
  /** Dialog header title. */
  title: ReactNode
  /** Body text describing the action and its consequences. */
  message: ReactNode
  /** Confirm button label. Defaults to "Confirm". */
  confirmLabel?: string
  /** Cancel button label. Defaults to "Cancel". */
  cancelLabel?: string
  /**
   * When true, renders the confirm button with the danger/red variant.
   * Use for irreversible destructive actions (delete, revoke key, etc.).
   */
  danger?: boolean
  /** Called when the user confirms the action. */
  onConfirm: () => void
  /** Called when the user cancels (backdrop click, Escape, or cancel button). */
  onCancel: () => void
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Styled confirmation dialog built on the Modal primitive.
 *
 * Replaces browser-native window.confirm() with a polished token-driven overlay.
 * The confirm button receives autoFocus so Enter naturally confirms;
 * Escape is handled by Modal's existing keydown listener and calls onCancel.
 * Pass danger=true to render a red confirm button for irreversible actions.
 *
 * Args:
 *   open: Controls visibility.
 *   title: Header title (string or ReactNode).
 *   message: Body text — should name the target and state consequences.
 *   confirmLabel: Label for the confirm button (default "Confirm").
 *   cancelLabel: Label for the cancel button (default "Cancel").
 *   danger: When true, confirm button uses the danger (red) variant.
 *   onConfirm: Callback invoked when the user confirms.
 *   onCancel: Callback invoked when the user cancels.
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // Footer: Cancel (subtle) left, Confirm (danger or primary) right.
  // autoFocus on the confirm button so Enter naturally triggers it.
  const footer = (
    <>
      <Button variant="subtle" onClick={onCancel}>
        {cancelLabel}
      </Button>
      {/* autoFocus lets Enter confirm; Escape is already handled by Modal. */}
      <Button variant={danger ? 'danger' : 'primary'} autoFocus onClick={onConfirm}>
        {confirmLabel}
      </Button>
    </>
  )

  return (
    <Modal
      isOpen={open}
      title={title}
      onClose={onCancel}
      footer={footer}
      maxWidth={400}
    >
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6 }}>
        {message}
      </p>
    </Modal>
  )
}
