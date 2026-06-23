// ====== Code Summary ======
// Renders a single row in the document list.  Displays the document's status
// dot, filename, status text, chunk count, pipeline duration, a Trace action
// button, and a ⋯ overflow menu (re-ingest / delete).

// ====== Standard Library Imports ======
import { useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import type { Document } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface DocRowProps {
  /** The document record to render. */
  doc: Document
  /** Owning collection — forwarded to delete / reingest calls. */
  collectionId: string
  /**
   * Whether this document is stale relative to the collection's current
   * pipeline version.  When true, a "périmé" badge and an inline re-index
   * button are shown.
   */
  isStale: boolean
  /** Collection's current pipeline version — shown in the staleness tooltip. */
  collectionPipelineVersion?: string
  /**
   * Called when the user clicks `[Trace]`.  The parent navigates to the
   * Pipeline tab and activates trace mode for the given document id.
   */
  onTrace: (docId: string) => void
  /** Called after the user confirms deletion via `window.confirm`. */
  onDelete: (docId: string) => void
  /** Called when the user selects "Re-ingest" in the overflow menu. */
  onReingest: (docId: string) => void
  /**
   * Called when the user clicks the filename / main row area to open the
   * document detail view.
   */
  onOpen: (docId: string) => void
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Returns the CSS class name for the status dot that matches the document's
 * pipeline status.
 *
 * Args:
 *   status: The document's `DocStatus` value.
 *
 * Returns:
 *   A CSS class string applied to the `.dot` element.
 */
function dotClass(status: Document['status']): string {
  switch (status) {
    case 'done':    return 'dot dot-done'
    case 'running': return 'dot dot-running spin'
    case 'error':   return 'dot dot-error'
    default:        return 'dot dot-pending'
  }
}

/**
 * Returns the inline colour style for the status text label.
 *
 * Args:
 *   status: The document's `DocStatus` value.
 *
 * Returns:
 *   A React CSSProperties object with a `color` rule.
 */
function statusColor(status: Document['status']): React.CSSProperties {
  switch (status) {
    case 'done':    return { color: 'var(--s-done)' }
    case 'running': return { color: 'var(--s-running)' }
    case 'error':   return { color: 'var(--s-error)' }
    default:        return { color: 'var(--s-pending)' }
  }
}

/**
 * Formats a pipeline duration in milliseconds as a human-readable string.
 * Returns "─" when no duration is available.
 *
 * Args:
 *   ms: Duration in milliseconds, or null/undefined.
 *
 * Returns:
 *   Formatted string such as "2.3s" or "─".
 */
function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '─'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * DocRow renders one document as a flex row inside the documents list.
 *
 * Layout (left → right):
 *   [dot] [filename] [status] [N chunks] [duration] [Trace] [⋯]
 *
 * The ⋯ overflow menu drops down below the button and closes automatically
 * when the user clicks anywhere outside the component.
 */
export function DocRow({ doc, collectionId: _collectionId, isStale, collectionPipelineVersion, onTrace, onDelete, onReingest, onOpen }: DocRowProps) {
  // 1. Local state: whether the overflow dropdown is visible.
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // 2. Close the menu when the user clicks outside the row's menu container.
  useEffect(() => {
    if (!menuOpen) return

    function handleOutsideClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [menuOpen])

  // 3. Derived display values.
  const filename    = doc.filename ?? doc.id
  const chunkCount  = doc.chunk_count ?? '─'
  const duration    = formatDuration(
    // `pipeline_duration_ms` may not be present on older generated types; fall
    // back gracefully by casting to any.
    (doc as Record<string, unknown>)['pipeline_duration_ms'] as number | null,
  )
  const canTrace    = doc.status === 'done'

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Requests deletion after a browser confirmation prompt.
   */
  function handleDelete() {
    setMenuOpen(false)
    if (window.confirm(`Delete "${filename}"? This cannot be undone.`)) {
      onDelete(doc.id)
    }
  }

  /**
   * Requests re-ingestion and closes the menu.
   */
  function handleReingest() {
    setMenuOpen(false)
    onReingest(doc.id)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="doc-row">
      {/* Status dot — spinning when running */}
      <span className={dotClass(doc.status)} />

      {/* Filename — clickable to open the detail view */}
      <span
        className="doc-row-name"
        title={filename}
        style={{ cursor: 'pointer' }}
        onClick={() => onOpen(doc.id)}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && onOpen(doc.id)}
      >
        {filename}
      </span>

      {/* Staleness badge — only when the doc's pipeline version is outdated */}
      {isStale && (
        <span
          className="tag doc-stale-badge"
          title={
            `Traité avec le pipeline ${doc.pipeline_version}` +
            (collectionPipelineVersion ? `, config actuelle ${collectionPipelineVersion}` : '') +
            ' — réindexation requise pour refléter les changements de pipeline/embedding/champs recherchables.'
          }
        >
          Périmé — à réindexer
        </span>
      )}

      {/* Status text + chunk count + duration */}
      <span className="doc-row-meta">
        <span style={statusColor(doc.status)}>{doc.status}</span>
        <span>{chunkCount !== '─' ? `${chunkCount} chunks` : '─'}</span>
        <span>{duration}</span>
      </span>

      {/* Actions: inline reingest (when stale) + Trace button + overflow menu */}
      <span className="doc-row-actions">
        {/* Inline re-index — surfaced directly in the row when the doc is stale */}
        {isStale && (
          <button
            type="button"
            className="btn-icon doc-row-reingest"
            title="Réindexer (config mise à jour)"
            onClick={() => onReingest(doc.id)}
          >
            ↻
          </button>
        )}

        {/* Trace — disabled until the document has finished processing */}
        <button
          type="button"
          className="btn-icon"
          disabled={!canTrace}
          title={canTrace ? 'Open in pipeline trace' : 'Available once processing is done'}
          onClick={() => onTrace(doc.id)}
        >
          Trace
        </button>

        {/* Overflow menu */}
        <div className="doc-menu" ref={menuRef}>
          <button
            type="button"
            className="btn-icon"
            title="More actions"
            onClick={() => setMenuOpen(prev => !prev)}
          >
            ⋯
          </button>

          {menuOpen && (
            <div className="doc-menu-dropdown">
              <button
                type="button"
                className="doc-menu-item"
                onClick={handleReingest}
              >
                Re-ingest
              </button>
              <button
                type="button"
                className="doc-menu-item doc-menu-item-danger"
                onClick={handleDelete}
              >
                Delete
              </button>
            </div>
          )}
        </div>
      </span>
    </div>
  )
}

export default DocRow
