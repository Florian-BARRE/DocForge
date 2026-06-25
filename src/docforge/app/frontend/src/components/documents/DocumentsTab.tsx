// ====== Code Summary ======
// DocumentsTab renders the Documents sub-tab for a selected collection.
// It owns the document list, a compact drop-zone for uploads, a live SSE stream
// that refreshes the list on job/stage events (with a 2 s polling fallback), and
// delegates per-row actions to DocRow.

// ====== Standard Library Imports ======
import { useCallback, useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import {
  deleteDocument,
  getConfigState,
  ingestDocument,
  listDocuments,
  reingestDocument,
  streamCollectionDocuments,
} from '../../api/client'
import type { ConfigState, Document, MetaField } from '../../api/types'
import { DocDetailView } from './DocDetailView'
import { DocRow } from './DocRow'
import { MetadataInputForm } from './MetadataInputForm'

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
  /**
   * When false, the upload drop-zone, metadata form, reindex banner, and
   * all per-row write actions (reingest / delete) are hidden.
   * Read-only users can browse and trace documents but cannot mutate them.
   */
  canWrite?: boolean
}

// ── Constants ────────────────────────────────────────────────────────────────

// Collapse bursts of SSE events (e.g. rapid stage.progress) into a single reload.
const REFETCH_DEBOUNCE_MS = 500
// Fallback polling cadence, used only when the SSE stream errors out.
const FALLBACK_POLL_MS = 2000

// ── Component ────────────────────────────────────────────────────────────────

/**
 * DocumentsTab is the main view for the Documents sub-tab.
 *
 * Responsibilities:
 * - Fetches and displays the document list for the active collection.
 * - Subscribes to a collection-scoped SSE stream and refreshes the list (debounced)
 *   on job/stage events, falling back to 2 s polling if the stream fails.
 * - Provides a compact drag-and-drop upload zone at the top.
 * - Forwards per-row actions (trace, delete, reingest) to the API layer and
 *   refreshes the list on completion.
 */
export function DocumentsTab({ collectionId, onTrace, canWrite = true }: DocumentsTabProps) {
  // ── State ──────────────────────────────────────────────────────────────

  const [docs, setDocs]               = useState<Document[]>([])
  const [isLoading, setIsLoading]     = useState(true)
  const [isDragging, setIsDragging]   = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  // When set, the detail view for this document id replaces the list.
  const [detailDocId, setDetailDocId] = useState<string | null>(null)

  // Collection config state — used to derive user-defined metadata fields for the form.
  const [configState, setConfigState] = useState<ConfigState | null>(null)
  // Metadata values the user has entered — passed to ingestDocument on upload.
  const [metaValues, setMetaValues]   = useState<Record<string, unknown>>({})
  // Whether the metadata input form is expanded.
  const [metaOpen, setMetaOpen]       = useState(false)

  // Bulk reindex progress — null when idle, otherwise {done, total} while running.
  const [reindexProgress, setReindexProgress] =
    useState<{ done: number; total: number } | null>(null)

  // Hidden file input used for click-to-upload.
  const inputRef = useRef<HTMLInputElement>(null)

  // Live SSE stream handle for this collection's document updates.
  const esRef = useRef<EventSource | null>(null)
  // Debounce handle so a burst of events triggers a single list reload.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Fallback polling interval — started only if the SSE stream errors out.
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
    setMetaValues({})
    fetchDocuments().finally(() => setIsLoading(false))
  }, [fetchDocuments])

  // 1b. Fetch config state to derive user-defined metadata fields.
  useEffect(() => {
    let cancelled = false
    getConfigState(collectionId)
      .then(cfg => { if (!cancelled) setConfigState(cfg) })
      .catch(() => { /* non-fatal */ })
    return () => { cancelled = true }
  }, [collectionId])

  // 2. Live updates — subscribe to a collection-scoped SSE stream and reload the
  //    list (debounced) on each job/stage event. EventSource reconnects natively;
  //    if it errors out we fall back to the legacy 2 s polling loop.
  useEffect(() => {
    // Debounced reload — collapses bursts of stage.progress events into one fetch.
    const scheduleRefetch = () => {
      // An event means the SSE stream is live again: stop any polling fallback a prior
      // onerror started, otherwise the list would be fetched twice indefinitely.
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      if (debounceRef.current !== null) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => { void fetchDocuments() }, REFETCH_DEBOUNCE_MS)
    }

    // Start the polling fallback once (guarded so onerror can't stack intervals).
    const startPolling = () => {
      if (pollRef.current !== null) return
      pollRef.current = setInterval(() => { void fetchDocuments() }, FALLBACK_POLL_MS)
    }

    // 2a. Open the stream and wire the two relevant typed events to a refetch.
    const es = streamCollectionDocuments(collectionId)
    esRef.current = es
    es.addEventListener('job.updated', scheduleRefetch)
    es.addEventListener('stage.progress', scheduleRefetch)
    es.onerror = startPolling

    // 2b. Tear everything down on unmount / collection change.
    return () => {
      es.close()
      esRef.current = null
      if (debounceRef.current !== null) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [collectionId, fetchDocuments])

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
      // 2. Submit the file to the API, including any user-entered metadata.
      await ingestDocument(collectionId, file, Object.keys(metaValues).length > 0 ? metaValues : undefined)

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

  /**
   * Re-index every stale document sequentially.
   *
   * There is no collection-level reindex endpoint, so this loops over the
   * provided stale documents and calls `reingestDocument` for each, surfacing
   * progress via `reindexProgress` and refreshing the list once complete.
   *
   * Args:
   *   staleDocs: The documents whose pipeline version is outdated.
   */
  async function handleReindexAll(staleDocs: Document[]) {
    // 1. Guard against an empty set or a re-entrant click.
    if (staleDocs.length === 0 || reindexProgress !== null) return
    setUploadError(null)
    setReindexProgress({ done: 0, total: staleDocs.length })

    try {
      // 2. Re-ingest each stale document in order, updating progress as we go.
      for (let i = 0; i < staleDocs.length; i++) {
        await reingestDocument(collectionId, staleDocs[i].id)
        setReindexProgress({ done: i + 1, total: staleDocs.length })
      }

      // 3. Refresh the list so the new statuses / versions appear.
      await fetchDocuments()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Re-index failed')
    } finally {
      setReindexProgress(null)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  // ── Detail view shortcut ──────────────────────────────────────────────────

  // When a document is selected for detail, render DocDetailView in place of
  // the list — the drop zone and list are not needed in this mode.
  if (detailDocId !== null) {
    return (
      <DocDetailView
        collectionId={collectionId}
        docId={detailDocId}
        onBack={() => setDetailDocId(null)}
      />
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const dropZoneClass = [
    'documents-drop-zone',
    isDragging ? 'documents-drop-zone-dragging' : '',
  ]
    .filter(Boolean)
    .join(' ')

  // Staleness is computed server-side (precise + reversible): a document is stale only when
  // the index-relevant config it was processed with differs from the current config.
  const collectionPipelineVersion = configState?.pipeline_version
  const staleDocs = docs.filter(d => d.stale === true)

  // Aggregate the exact per-document causes (deduplicated) for the banner.
  const staleCauses = Array.from(
    new Set(staleDocs.flatMap(d => d.stale_reasons ?? []))
  )

  const showReindexBanner = staleDocs.length > 0
  const isReindexing = reindexProgress !== null

  return (
    <div className="documents-tab">
      {/* ── Drop zone — only rendered for users with write access ── */}
      {canWrite && (
        <>
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
        </>
      )}

      {/* Upload / delete error banner */}
      {uploadError && (
        <div className="documents-drop-error">{uploadError}</div>
      )}

      {/* ── Metadata input form — only shown to users with write access ── */}
      {canWrite && configState && (() => {
        const userFields: MetaField[] = configState.metadata_fields.filter(f => !f.is_system)
        return (
          <MetadataInputForm
            fields={userFields}
            onChange={setMetaValues}
            isOpen={metaOpen}
            onToggle={() => setMetaOpen(o => !o)}
          />
        )
      })()}

      {/* ── Reindex banner — shown to all users; action button only for write access ── */}
      {showReindexBanner && (
        <div className="reindex-banner">
          <span>
            {staleDocs.length} document(s) pending reindex — their indexing configuration
            no longer matches the current pipeline config.
            {staleCauses.length > 0 && (
              <span className="reindex-banner-cause"> Cause: {staleCauses.join('; ')}.</span>
            )}
          </span>
          {/* Reindex action only for users with write permission. */}
          {canWrite && (
            <div className="reindex-banner-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={isReindexing || staleDocs.length === 0}
                onClick={() => handleReindexAll(staleDocs)}
              >
                {isReindexing && reindexProgress
                  ? `Reindexing… (${reindexProgress.done}/${reindexProgress.total})`
                  : 'Reindex all'}
              </button>
            </div>
          )}
        </div>
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
              isStale={doc.stale === true}
              staleReasons={doc.stale_reasons ?? []}
              collectionPipelineVersion={collectionPipelineVersion}
              onTrace={onTrace}
              onDelete={handleDelete}
              onReingest={handleReingest}
              onOpen={setDetailDocId}
              canWrite={canWrite}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default DocumentsTab
