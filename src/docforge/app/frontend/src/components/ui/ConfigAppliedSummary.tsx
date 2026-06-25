// ====== Code Summary ======
// Compact transparency summary shown after a config save.
// Renders the "applied" envelope returned by the backend: whether a reindex is
// required, which top-level keys were provided vs defaulted, human-readable
// notes, and any non-blocking warnings. Only non-empty sections are rendered;
// when there is nothing to show (or the envelope is null) the component renders
// nothing.

// ====== Internal Project Imports ======
import type { ConfigApplied } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConfigAppliedSummaryProps {
  /** Transparency envelope from the last save, or null when none is available. */
  applied: ConfigApplied | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Render the post-save transparency envelope in a compact, muted block.
 *
 * Shows, in order and only when present:
 *   - a "Reindex required" badge when {@link ConfigApplied.needs_reindex};
 *   - a "Provided" line listing explicitly provided top-level keys;
 *   - a "Defaulted" line listing keys filled from defaults;
 *   - a bulleted list of human-readable notes;
 *   - each warning message highlighted in the running/warning colour.
 *
 * Args:
 *   applied: The transparency envelope, or null to render nothing.
 *
 * Returns:
 *   JSX.Element | null: The summary block, or null when there is nothing to show.
 */
export function ConfigAppliedSummary({ applied }: ConfigAppliedSummaryProps) {
  // 1. Nothing to render when no envelope is available.
  if (!applied) return null

  const provided = applied.provided ?? []
  const defaulted = applied.defaulted ?? []
  const notes = applied.notes ?? []
  const warnings = applied.warnings ?? []
  const reindexReasons = applied.reindex_reasons ?? []

  // 2. Skip rendering entirely when every section is empty.
  const hasContent =
    applied.needs_reindex ||
    provided.length > 0 ||
    defaulted.length > 0 ||
    notes.length > 0 ||
    warnings.length > 0
  if (!hasContent) return null

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="config-applied-summary">
      {applied.needs_reindex && (
        <span className="tag" style={{ color: 'var(--s-running)' }}>
          Reindex required
        </span>
      )}

      {/* Exact cause(s) of the required reindex — empty for non-critical changes. */}
      {reindexReasons.length > 0 && (
        <ul className="config-applied-reasons">
          {reindexReasons.map((reason, i) => (
            <li key={i} style={{ color: 'var(--s-running)' }}>{reason}</li>
          ))}
        </ul>
      )}

      {provided.length > 0 && <div>Provided: {provided.join(', ')}</div>}

      {defaulted.length > 0 && <div>Defaulted: {defaulted.join(', ')}</div>}

      {notes.length > 0 && (
        <ul>
          {notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}

      {warnings.map((warning, i) => (
        <div key={i} style={{ color: 'var(--s-running)' }}>
          {warning.message}
        </div>
      ))}
    </div>
  )
}
