// ====== Code Summary ======
// DocumentsTab renders the Documents sub-tab for a selected collection.
// It owns the document list, a compact drop-zone for multi-file uploads, a live
// SSE stream that refreshes the list on job/stage events (with a 2 s polling
// fallback), a filter/sort toolbar, and delegates per-row actions to DocRow.

// ====== Standard Library Imports ======
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

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
import { EmptyState } from '../ui/primitives/EmptyState'
import { Spinner } from '../ui/primitives/Spinner'
import { DocDetailView } from './DocDetailView'
import { DocRow } from './DocRow'
import { DEFAULT_DOCS_FILTERS, DocsToolbar } from './DocsToolbar'
import type { DocsFilters } from './DocsToolbar'
import { MetadataInputForm } from './MetadataInputForm'
import { formatFileSize } from './detail/detailHelpers'

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
 * - Fetches and displays the document list for the active collection,
 *   honouring server-side status filter and sort controls in the toolbar.
 * - Subscribes to a collection-scoped SSE stream and refreshes the list
 *   (debounced) on job/stage events, falling back to 2 s polling if the
 *   stream fails.
 * - Provides a compact drag-and-drop upload zone accepting multiple files,
 *   which are ingested sequentially with per-file progress feedback.
 * - Forwards per-row actions (trace, delete, reingest) to the API layer and
 *   refreshes the list on completion.
 */
export function DocumentsTab({ collectionId, onTrace, canWrite = true }: DocumentsTabProps) {
  // ── State ──────────────────────────────────────────────────────────────

  const [docs, setDocs]               = useState<Document[]>([])
  const [isLoading, setIsLoading]     = useState(true)
  const [isDragging, setIsDragging]   = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  // Progress for multi-file uploads: current file index (1-based) + total.
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  // When set, the detail view for this document id replaces the list.
  const [detailDocId, setDetailDocId] = useState<string | null>(null)

  // Filter/sort state for the toolbar.  Server-side params are applied in
  // fetchDocuments via filtersRef; nameFilter is client-side only.
  const [filters, setFilters]   = useState<DocsFilters>(DEFAULT_DOCS_FILTERS)
  // Ref kept in sync with state so SSE handlers always read the latest params
  // without needing fetchDocuments to be recreated.
  const filtersRef = useRef<DocsFilters>(DEFAULT_DOCS_FILTERS)

  // Collection config state — used to derive user-defined metadata fields
  // and the dropzone format/size hint.
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
   * Fetches the document list using the current filter/sort params from
   * filtersRef.  Silently ignores errors (polling should not crash the tab).
   *
   * Reads from filtersRef so that SSE handlers always use the latest filter
   * state without requiring fetchDocuments to be recreated on every change.
   */
  const fetchDocuments = useCallback(async () => {
    const f = filtersRef.current
    try {
      const res = await listDocuments(collectionId, {
        status:     f.statusFilter || undefined,
        sort_by:    f.sortBy,
        sort_order: f.sortOrder,
      })
      setDocs(res.documents)
    } catch {
      // Intentionally suppressed — the list simply stays stale.
    }
  }, [collectionId])

  // 1. Initial fetch on mount / when collectionId changes.  Also resets the
  //    toolbar filters so stale settings from a previous collection do not apply.
  useEffect(() => {
    setIsLoading(true)
    setUploadError(null)
    setMetaValues({})
    // Reset toolbar filters to defaults when the active collection changes.
    const defaults = DEFAULT_DOCS_FILTERS
    setFilters(defaults)
    filtersRef.current = defaults
    fetchDocuments().finally(() => setIsLoading(false))
  }, [fetchDocuments])

  // 1b. Fetch config state to derive user-defined metadata fields + dropzone hint.
  useEffect(() => {
    let cancelled = false
    getConfigState(collectionId)
      .then(cfg => { if (!cancelled) setConfigState(cfg) })
      .catch(() => { /* non-fatal */ })
    return () => { cancelled = true }
  }, [collectionId])

  // 2. Live updates — subscribe to a collection-scoped SSE stream and reload the
  //    list (debounced) on each job/stage event.  EventSource reconnects natively;
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

  // ── Toolbar handler ────────────────────────────────────────────────────

  /**
   * Handles toolbar filter/sort changes.
   *
   * Updates the filters state and the ref synchronously.  When server-side
   * params (status, sort) change, triggers a list refetch immediately.
   * nameFilter changes are client-side and do not require a round-trip.
   *
   * Args:
   *   newFilters: The new filter/sort values from the toolbar.
   */
  function handleFiltersChange(newFilters: DocsFilters) {
    const serverChanged =
      newFilters.statusFilter !== filters.statusFilter ||
      newFilters.sortBy !== filters.sortBy ||
      newFilters.sortOrder !== filters.sortOrder

    // Synchronously update the ref so the next fetchDocuments call uses the
    // new params even before React re-renders.
    filtersRef.current = newFilters
    setFilters(newFilters)

    if (serverChanged) {
      void fetchDocuments()
    }
  }

  // ── Client-side filtered view ──────────────────────────────────────────

  // Apply the name filter client-side over the server-fetched page.
  // staleDocs is derived from the full docs list (not the name-filtered view)
  // so the reindex banner is accurate regardless of the current search.
  const visibleDocs = useMemo(() => {
    const q = filters.nameFilter.trim().toLowerCase()
    if (!q) return docs
    return docs.filter(d => (d.filename ?? d.id).toLowerCase().includes(q))
  }, [docs, filters.nameFilter])

  // ── Upload handler ─────────────────────────────────────────────────────

  /**
   * Uploads multiple files to the backend sequentially via `ingestDocument`,
   * then refreshes the document list.  Aggregates errors across all files and
   * surfaces a summary message in the error banner.
   *
   * Args:
   *   files: Array of files to upload.
   */
  async function handleMultiUpload(files: File[]) {
    if (isUploading || files.length === 0) return
    setIsUploading(true)
    setUploadError(null)
    setUploadProgress({ current: 0, total: files.length })

    const errors: string[] = []
    try {
      for (let i = 0; i < files.length; i++) {
        setUploadProgress({ current: i + 1, total: files.length })
        try {
          // Include user-entered metadata only when provided.
          await ingestDocument(
            collectionId,
            files[i],
            Object.keys(metaValues).length > 0 ? metaValues : undefined,
          )
        } catch (err) {
          errors.push(`${files[i].name}: ${err instanceof Error ? err.message : 'Upload failed'}`)
        }
      }
      // Refresh once after all files are processed.
      await fetchDocuments()
      if (errors.length > 0) {
        // Surface up to 3 errors; truncate the rest.
        const shown = errors.slice(0, 3)
        const extra = errors.length - shown.length
        setUploadError(
          shown.join(' | ') + (extra > 0 ? ` (+${extra} more errors)` : ''),
        )
      }
    } finally {
      setIsUploading(false)
      setUploadProgress(null)
      // Reset the hidden input so the same files can be re-uploaded.
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
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) void handleMultiUpload(files)
  }

  function handleZoneClick() {
    inputRef.current?.click()
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    if (files.length > 0) void handleMultiUpload(files)
  }

  // ── Per-row action handlers ────────────────────────────────────────────

  /**
   * Deletes a document and refreshes the list.
   *
   * Args:
   *   docId: The UUID of the document to delete.
   */
  async function handleDelete(docId: string) {
    setUploadError(null)
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
    setUploadError(null)
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
   * Args:
   *   staleDocs: The documents whose pipeline version is outdated.
   */
  async function handleReindexAll(staleDocs: Document[]) {
    if (staleDocs.length === 0 || reindexProgress !== null) return
    setUploadError(null)
    setReindexProgress({ done: 0, total: staleDocs.length })

    try {
      for (let i = 0; i < staleDocs.length; i++) {
        await reingestDocument(collectionId, staleDocs[i].id)
        setReindexProgress({ done: i + 1, total: staleDocs.length })
      }
      await fetchDocuments()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Re-index failed')
    } finally {
      setReindexProgress(null)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  // When a document is selected for detail, render DocDetailView in place of
  // the list — the drop zone and list are not needed in this mode.
  if (detailDocId !== null) {
    return (
      <DocDetailView
        collectionId={collectionId}
        docId={detailDocId}
        onBack={() => setDetailDocId(null)}
        canWrite={canWrite}
      />
    )
  }

  // ── Derived values ────────────────────────────────────────────────────────

  const dropZoneClass = [
    'documents-drop-zone',
    isDragging ? 'documents-drop-zone-dragging' : '',
  ]
    .filter(Boolean)
    .join(' ')

  // Staleness derived from the full server-fetched docs (ignores nameFilter so
  // the reindex banner is accurate regardless of the current name search).
  const collectionPipelineVersion = configState?.pipeline_version
  const staleDocs = docs.filter(d => d.stale === true)
  const staleCauses = Array.from(
    new Set(staleDocs.flatMap(d => d.stale_reasons ?? []))
  )
  const showReindexBanner = staleDocs.length > 0
  const isReindexing = reindexProgress !== null

  // Upload label reflects per-file progress for multi-file batches.
  const uploadLabel = uploadProgress
    ? `Uploading ${uploadProgress.current}/${uploadProgress.total}…`
    : 'Uploading…'

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
            aria-label="Drop files here or click to upload"
          >
            {isUploading ? (
              <span className="text-muted">{uploadLabel}</span>
            ) : (
              <>
                <span className="text-muted">
                  {isDragging ? 'Drop to upload' : 'Drop files here or click to upload'}
                </span>
                {/* Accepted formats + max size hint from collection config */}
                {configState && (
                  <span className="drop-zone-hint">
                    {configState.supported_formats.slice(0, 8).map(f => f.toUpperCase()).join(' · ')}
                    {configState.supported_formats.length > 8 ? ' …' : ''}
                    {' · max '}
                    {formatFileSize(configState.max_file_size_bytes)}
                  </span>
                )}
              </>
            )}
          </div>

          {/* Hidden file input — multiple files allowed */}
          <input
            ref={inputRef}
            type="file"
            multiple
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
        </>
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

      {/* ── Filter / sort toolbar — shown when there are documents ── */}
      {docs.length > 0 && (
        <DocsToolbar filters={filters} onFiltersChange={handleFiltersChange} />
      )}

      {/* ── Dismissible error banner — replaces the small drop-error style ── */}
      {uploadError && (
        <div className="docs-error-banner">
          <span>{uploadError}</span>
          <button
            type="button"
            className="docs-error-dismiss"
            aria-label="Dismiss error"
            onClick={() => setUploadError(null)}
          >
            ×
          </button>
        </div>
      )}

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '16px 0' }}>
            <Spinner size={14} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading documents…</span>
          </div>
        ) : docs.length === 0 ? (
          <EmptyState
            icon="📄"
            message="No documents yet"
            description="Drop a file above to start ingesting."
          />
        ) : visibleDocs.length === 0 ? (
          <EmptyState
            message="No matching documents"
            description="Try changing the filename filter."
          />
        ) : (
          visibleDocs.map(doc => (
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
