// ====== Code Summary ======
// Presentational save bar shown at the bottom of every configuration panel.
// Surfaces the draft status ("unsaved changes" / saving / saved / error) on the
// left and the Discard / Save action buttons on the right. Purely presentational:
// it owns no state and delegates all behavior to the supplied callbacks.

// ====== Internal Project Imports ======
import type { ConfigApplied } from '../../api/types'
import type { DraftStatus } from '../../hooks/useConfigDraft'

// ====== Local Project Imports ======
import { ConfigAppliedSummary } from './ConfigAppliedSummary'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConfigSaveBarProps {
  /** Current draft lifecycle status. */
  status: DraftStatus
  /** Whether there are unsaved changes (gates both buttons). */
  isDirty: boolean
  /** Invoked when the user clicks "Save". */
  onSave: () => void
  /** Invoked when the user clicks "Cancel". */
  onDiscard: () => void
  /** Transparency envelope from the last save, shown above the action row. */
  applied?: ConfigApplied | null
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
      return <span style={{ color: 'var(--s-running)' }}>● Unsaved changes</span>
    case 'saving':
      return <span style={{ color: 'var(--text-dim)' }}>Saving…</span>
    case 'saved':
      return <span style={{ color: 'var(--s-done)' }}>✓ Saved</span>
    case 'error':
      return <span style={{ color: 'var(--s-error)' }}>✗ Save failed</span>
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
 *   applied:   Optional transparency envelope from the last save.
 */
export function ConfigSaveBar({ status, isDirty, onSave, onDiscard, applied }: ConfigSaveBarProps) {
  return (
    <div className="config-save-bar-wrap">
      {/* Transparency summary of what the last save actually applied. */}
      <ConfigAppliedSummary applied={applied ?? null} />

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
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!isDirty || status === 'saving'}
            onClick={onSave}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
