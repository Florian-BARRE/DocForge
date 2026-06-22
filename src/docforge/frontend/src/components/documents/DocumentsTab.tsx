// ====== Code Summary ======
// DocumentsTab renders the Documents sub-tab for a selected collection.
// It owns the document list, a compact drop-zone for uploads, background
// polling for in-progress documents, and delegates per-row actions to DocRow.

// ====== Standard Library Imports ======
import { useCallback, useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import {
  deleteDocument,
  ingestDocument,
  listDocuments,
  reingestDocument,
} from '../../api/client'
import type { Document } from '../../api/types'
import { DocRow } from './DocRow'

// ── Types ────────────────────────────────────────────────────────────────────

interface DocumentsTabProps {
  /** The active collection to display documents for. */
  collectionId: string
  /**
   * Called when the user clicks `[Trace]` on a document row.
   * The parent (App) should set the active document id and navigate to the
   * Pipeline tab.
   */
  onTrace: (docId: string) => void
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Returns `true` when at least one document in the list is still in-flight
 * (pending or running).  Used to decide whether polling should continue.
 *
 * Args:
 *   docs: Current document list.
 *
 * Returns:
 *   Boolean indicating whether any document needs polling.
 */
function hasActiveDocuments(docs: Document[]): boolean {
  return docs.some(d => d.status === 'pending' || d.status === 'running')
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * DocumentsTab is the main view for the Documents sub-tab.
 *
 * Responsibilities:
 * - Fetches and displays the document list for the active collection.
 * - Polls the list every 2 s while any document is pending/running.
 * - Provides a compact drag-and-drop upload zone at the top.
 * - Forwards per-row actions (trace, delete, reingest) to the API layer and
 *   refreshes the list on completion.
 */
export function DocumentsTab({ collectionId, onTrace }: DocumentsTabProps) {
  // ── State ──────────────────────────────────────────────────────────────

  const [docs, setDocs]               = useState<Document[]>([])
  const [isLoading, setIsLoading]     = useState(true)
  const [isDragging, setIsDragging]   = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  // Hidden file input used for click-to-upload.
  const inputRef = useRef<HTMLInputElement>(null)

  // Interval handle for the polling loop — kept in a ref so the cleanup
  // function always sees the most recent handle.
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Data fetching ──────────────────────────────────────────────────────

  /**
   * Fetches the full document list and updates state.
   * Silently ignores errors (polling should not crash the tab).
   */
  const fetchDocuments = useCallback(async () => {
    try {
      const res = await listDocuments(collectionId)
      setDocs(res.documents)
    } catch {
      // Intentionally suppressed — the list simply stays stale.
    }
  }, [collectionId])

  // 1. Initial fetch on mount / when collectionId changes.
  useEffect(() => {
    setIsLoading(true)
    setUploadError(null)
    fetchDocuments().finally(() => setIsLoading(false))
  }, [fetchDocuments])

  // 2. Polling loop — active only while at least one document is in-flight.
  useEffect(() => {
    // Clear any previous interval before deciding whether to start a new one.
    if (pollRef.current !== null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }

    if (!hasActiveDocuments(docs)) return

    pollRef.current = setInterval(async () => {
      await fetchDocuments()
    }, 2000)

    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [docs, fetchDocuments])

  // ── Upload handler ─────────────────────────────────────────────────────

  /**
   * Uploads a single file to the backend via `ingestDocument`, then refreshes
   * the document list.  Sets `uploadError` on failure.
   *
   * Args:
   *   file: The file selected by the user (drag-and-drop or file picker).
   */
  async function handleUpload(file: File) {
    // 1. Guard against concurrent uploads.
    if (isUploading) return
    setIsUploading(true)
    setUploadError(null)

    try {
      // 2. Submit the file to the API.
      await ingestDocument(collectionId, file)

      // 3. Refresh the document list to show the new entry.
      await fetchDocuments()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setIsUploading(false)
      // Reset the hidden input so the same file can be re-uploaded.
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  // ── Drop zone event handlers ───────────────────────────────────────────

  function handleDragEnter(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(true)
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault()
    // Only clear when leaving the zone entirely — dragLeave fires for child elements too.
    if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
      setIsDragging(false)
    }
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault()
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }

  function handleZoneClick() {
    inputRef.current?.click()
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleUpload(file)
  }

  // ── Per-row action handlers ────────────────────────────────────────────

  /**
   * Deletes a document and refreshes the list.
   *
   * Args:
   *   docId: The UUID of the document to delete.
   */
  async function handleDelete(docId: string) {
    try {
      await deleteDocument(collectionId, docId)
      await fetchDocuments()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  /**
   * Re-ingest a previously processed document.
   *
   * Args:
   *   docId: The UUID of the document to re-ingest.
   */
  async function handleReingest(docId: string) {
    try {
      await reingestDocument(collectionId, docId)
      await fetchDocuments()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Re-ingest failed')
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const dropZoneClass = [
    'documents-drop-zone',
    isDragging ? 'documents-drop-zone-dragging' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="documents-tab">
      {/* ── Drop zone ── */}
      <div
        className={dropZoneClass}
        onClick={handleZoneClick}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && handleZoneClick()}
        aria-label="Drop a file here or click to upload"
      >
        {isUploading ? (
          <span className="text-muted">Uploading…</span>
        ) : (
          <span className="text-muted">
            {isDragging ? 'Drop to upload' : 'Drop a file here or click to upload'}
          </span>
        )}
      </div>

      {/* Hidden file input — triggered by click on the drop zone */}
      <input
        ref={inputRef}
        type="file"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />

      {/* Upload error banner */}
      {uploadError && (
        <div className="documents-drop-error">{uploadError}</div>
      )}

      {/* ── Document list ── */}
      <div className="documents-list">
        {isLoading ? (
          <div className="text-dim" style={{ padding: '16px 0', fontSize: 12 }}>
            Loading documents…
          </div>
        ) : docs.length === 0 ? (
          <div className="text-dim" style={{ padding: '16px 0', fontSize: 12 }}>
            No documents yet — drop a file above to get started.
          </div>
        ) : (
          docs.map(doc => (
            <DocRow
              key={doc.id}
              doc={doc}
              collectionId={collectionId}
              onTrace={onTrace}
              onDelete={handleDelete}
              onReingest={handleReingest}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default DocumentsTab
