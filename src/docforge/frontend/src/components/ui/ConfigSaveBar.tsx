// ====== Code Summary ======
// Presentational save bar shown at the bottom of every configuration panel.
// Surfaces the draft status ("unsaved changes" / saving / saved / error) on the
// left and the Discard / Save action buttons on the right. Purely presentational:
// it owns no state and delegates all behavior to the supplied callbacks.

// ====== Internal Project Imports ======
import type { DraftStatus } from '../../hooks/useConfigDraft'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConfigSaveBarProps {
  /** Current draft lifecycle status. */
  status: DraftStatus
  /** Whether there are unsaved changes (gates both buttons). */
  isDirty: boolean
  /** Invoked when the user clicks "Enregistrer". */
  onSave: () => void
  /** Invoked when the user clicks "Annuler". */
  onDiscard: () => void
}

// ── Status indicator ────────────────────────────────────────────────────────────

/**
 * Render the left-hand status label for the current draft state.
 *
 * Returns null for the 'clean' state so the indicator collapses cleanly.
 *
 * Args:
 *   status: Current draft lifecycle status.
 *
 * Returns:
 *   JSX.Element | null: The styled status label, or null when clean.
 */
function StatusIndicator({ status }: { status: DraftStatus }) {
  switch (status) {
    case 'dirty':
      return <span style={{ color: 'var(--s-running)' }}>● Modifications non enregistrées</span>
    case 'saving':
      return <span style={{ color: 'var(--text-dim)' }}>Enregistrement…</span>
    case 'saved':
      return <span style={{ color: 'var(--s-done)' }}>✓ Enregistré</span>
    case 'error':
      return <span style={{ color: 'var(--s-error)' }}>✗ Échec de l&apos;enregistrement</span>
    case 'clean':
    default:
      return null
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Save bar with a status indicator and Discard / Save actions.
 *
 * Both buttons are disabled when there are no pending changes; the Save button is
 * additionally disabled while a save is in flight.
 *
 * Args:
 *   status:    Current draft lifecycle status.
 *   isDirty:   Whether unsaved changes exist.
 *   onSave:    Save handler.
 *   onDiscard: Discard handler.
 */
export function ConfigSaveBar({ status, isDirty, onSave, onDiscard }: ConfigSaveBarProps) {
  return (
    <div className="config-save-bar">
      <div className="config-save-status">
        <StatusIndicator status={status} />
      </div>
      <div className="config-save-actions">
        <button
          type="button"
          className="btn btn-ghost"
          disabled={!isDirty}
          onClick={onDiscard}
        >
          Annuler
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!isDirty || status === 'saving'}
          onClick={onSave}
        >
          Enregistrer
        </button>
      </div>
    </div>
  )
}
