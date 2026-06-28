// ====== Code Summary ======
// Renders a single row in the document list.  Displays the document's status
// dot, filename, status text, chunk count, pipeline duration, a Trace action
// button, and a ⋯ overflow menu (re-ingest / delete).

// ====== Standard Library Imports ======
import { useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import type { Document } from '../../api/types'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { formatDuration } from './detail/detailHelpers'

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
  /** Exact, human-readable reasons the document is stale (shown in the badge tooltip). */
  staleReasons?: string[]
  /** Collection's current pipeline version — shown in the staleness tooltip. */
  collectionPipelineVersion?: string
  /**
   * Called when the user clicks `[Trace]`.  The parent navigates to the
   * Pipeline tab and activates trace mode for the given document id.
   */
  onTrace: (docId: string) => void
  /** Called after the user confirms deletion in the ConfirmDialog. */
  onDelete: (docId: string) => void
  /** Called when the user selects "Re-ingest" in the overflow menu. */
  onReingest: (docId: string) => void
  /**
   * Called when the user clicks the filename / main row area to open the
   * document detail view.
   */
  onOpen: (docId: string) => void
  /**
   * When false, the reingest and delete actions are hidden.
   * Read-only users can view and trace documents but cannot mutate them.
   */
  canWrite?: boolean
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
export function DocRow({ doc, collectionId: _collectionId, isStale, staleReasons, collectionPipelineVersion, onTrace, onDelete, onReingest, onOpen, canWrite = true }: DocRowProps) {
  // 1. Local state: overflow dropdown visibility + delete confirmation dialog.
  const [menuOpen, setMenuOpen] = useState(false)
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false)
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
  // pipeline_duration_ms is now a typed field on Document; null means not yet complete.
  const durationMs  = doc.pipeline_duration_ms
  const canTrace    = doc.status === 'done'

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Opens the styled ConfirmDialog to gate the destructive delete action.
   */
  function handleDelete() {
    setMenuOpen(false)
    setDeleteConfirmOpen(true)
  }

  /**
   * Executes the deletion after the user confirms in the dialog.
   */
  function handleDeleteConfirmed() {
    setDeleteConfirmOpen(false)
    onDelete(doc.id)
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
    <>
    {/* Styled delete confirmation — replaces window.confirm() */}
    <ConfirmDialog
      open={deleteConfirmOpen}
      title="Delete document"
      message={`Delete "${filename}"? This removes its chunks and vectors. This cannot be undone.`}
      confirmLabel="Delete"
      cancelLabel="Cancel"
      danger
      onConfirm={handleDeleteConfirmed}
      onCancel={() => setDeleteConfirmOpen(false)}
    />
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
            (staleReasons && staleReasons.length > 0
              ? `Cause: ${staleReasons.join(' ; ')}.\n`
              : '') +
            `Processed with pipeline ${doc.pipeline_version}` +
            (collectionPipelineVersion ? `, current config ${collectionPipelineVersion}` : '') +
            ' — reindex required.'
          }
        >
          Stale — reindex required
        </span>
      )}

      {/* Status text + chunk count + duration (duration hidden when null) */}
      <span className="doc-row-meta">
        <span style={statusColor(doc.status)}>{doc.status}</span>
        <span>{chunkCount !== '─' ? `${chunkCount} chunks` : '─'}</span>
        {durationMs != null && <span>{formatDuration(durationMs)}</span>}
      </span>

      {/* Actions: inline reingest (when stale, write-only) + Trace + overflow menu (write-only) */}
      <span className="doc-row-actions">
        {/* Inline re-index — only shown to users with write access. */}
        {isStale && canWrite && (
          <button
            type="button"
            className="btn-icon doc-row-reingest"
            title="Re-index (config updated)"
            onClick={() => onReingest(doc.id)}
          >
            ↻
          </button>
        )}

        {/* Trace — disabled until the document has finished processing. */}
        <button
          type="button"
          className="btn-icon"
          disabled={!canTrace}
          title={canTrace ? 'Open in pipeline trace' : 'Available once processing is done'}
          onClick={() => onTrace(doc.id)}
        >
          Trace
        </button>

        {/* Overflow menu — only rendered for users with write access. */}
        {canWrite && (
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
        )}
      </span>
    </div>
    </>
  )
}

export default DocRow
