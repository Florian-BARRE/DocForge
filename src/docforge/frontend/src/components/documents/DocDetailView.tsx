// ====== Code Summary ======
// DocDetailView renders a full-screen detail view for a single document.
// Provides sub-tab navigation across: Overview, IR, Chunks, Pages, Downloads.
// Replaces the documents list when a user opens a document from DocRow.

// ====== Standard Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import {
  getDocument,
  getDocumentMarkdown,
  getDocumentOriginal,
  getDocumentPdf,
  getPage,
  getPageScreenshotUrl,
  listPages,
} from '../../api/client'
import type { Document, PageDetailResponse, PageInfo, PresignedUrlResponse } from '../../api/types'
import { ChunkBrowser } from '../inspect/ChunkBrowser'
import { S1Block } from '../inspect/stages/S1Block'

// ── Types ─────────────────────────────────────────────────────────────────────

type DetailTab = 'overview' | 'ir' | 'chunks' | 'pages' | 'downloads'

interface DocDetailViewProps {
  /** Collection the document belongs to. */
  collectionId: string
  /** UUID of the document to display. */
  docId: string
  /** Callback to return to the document list. */
  onBack: () => void
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Formats a file size in bytes to a human-readable string (KB or MB).
 *
 * Args:
 *   bytes: File size in bytes.
 *
 * Returns:
 *   Formatted string such as "1.2 MB" or "345 KB".
 */
function formatFileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${bytes} B`
}

/**
 * Formats a pipeline duration in milliseconds to a compact string.
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

/**
 * Returns the CSS class for the status dot matching a document's pipeline status.
 *
 * Args:
 *   status: Document pipeline status string.
 *
 * Returns:
 *   CSS class string for the dot element.
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
 * Returns the inline colour for status text labels.
 *
 * Args:
 *   status: Document pipeline status string.
 *
 * Returns:
 *   React CSSProperties with a color rule.
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
 * DocDetailView is a full-screen document inspector with sub-tab navigation.
 *
 * Fetches the document on mount, then renders five sub-tabs:
 *   - Overview: key/value metadata grid
 *   - IR:       per-page block inspector via S1Block
 *   - Chunks:   full chunk browser via ChunkBrowser
 *   - Pages:    screenshot thumbnails with expandable block detail
 *   - Downloads: presigned URL buttons for original / markdown / PDF
 *
 * Args:
 *   collectionId: UUID of the owning collection.
 *   docId:        UUID of the document to display.
 *   onBack:       Callback to navigate back to the document list.
 */
export function DocDetailView({ collectionId, docId, onBack }: DocDetailViewProps) {
  // ── State ──────────────────────────────────────────────────────────────
  const [doc, setDoc]             = useState<Document | null>(null)
  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError]         = useState<string | null>(null)

  // ── Data fetch ─────────────────────────────────────────────────────────

  // 1. Fetch document on mount / when docId changes.
  useEffect(() => {
    setIsLoading(true)
    setError(null)
    getDocument(collectionId, docId)
      .then(setDoc)
      .catch(err => setError(String(err)))
      .finally(() => setIsLoading(false))
  }, [collectionId, docId])

  // ── Render ────────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="doc-detail-view">
        <div className="doc-detail-body" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <span className="text-muted"><span className="spin">⟳</span> Loading document…</span>
        </div>
      </div>
    )
  }

  if (error || !doc) {
    return (
      <div className="doc-detail-view">
        <div className="doc-detail-body">
          <div className="error-banner">{error ?? 'Document not found.'}</div>
          <button type="button" className="btn" style={{ marginTop: 12 }} onClick={onBack}>
            ← Back
          </button>
        </div>
      </div>
    )
  }

  const filename = doc.filename ?? doc.id
  // `pipeline_duration_ms` may lag behind the generated types — cast safely.
  const pipelineDurationMs = (doc as Record<string, unknown>)['pipeline_duration_ms'] as number | null | undefined

  return (
    <div className="doc-detail-view">
      {/* ── Header ── */}
      <div className="doc-detail-header">
        <button type="button" className="btn-icon doc-detail-back" onClick={onBack} title="Back to list">
          ←
        </button>

        {/* Status dot + filename */}
        <span className={dotClass(doc.status)} />
        <span className="doc-detail-title" title={filename}>{filename}</span>

        {/* Status + badges */}
        <div className="doc-detail-badges">
          <span style={statusColor(doc.status)}>{doc.status}</span>
          <span className="tag">{doc.format}</span>
          <span className="tag">{formatFileSize(doc.file_size)}</span>
          {doc.chunk_count != null && (
            <span className="tag">{doc.chunk_count} chunks</span>
          )}
        </div>
      </div>

      {/* ── Sub-tab navigation ── */}
      <div className="doc-detail-tabs">
        {(['overview', 'ir', 'chunks', 'pages', 'downloads'] as DetailTab[]).map(tab => (
          <button
            key={tab}
            type="button"
            className={`doc-detail-tab ${activeTab === tab ? 'doc-detail-tab-active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* ── Tab body ── */}
      <div className="doc-detail-body">
        {activeTab === 'overview' && (
          <OverviewTab doc={doc} pipelineDurationMs={pipelineDurationMs} />
        )}
        {activeTab === 'ir' && (
          <div className="stage-panel" style={{ padding: 0 }}>
            <S1Block doc={doc} collectionId={collectionId} />
          </div>
        )}
        {activeTab === 'chunks' && (
          <ChunkBrowser doc={doc} collectionId={collectionId} />
        )}
        {activeTab === 'pages' && (
          <PagesTab collectionId={collectionId} docId={docId} doc={doc} />
        )}
        {activeTab === 'downloads' && (
          <DownloadsTab collectionId={collectionId} docId={docId} doc={doc} />
        )}
      </div>
    </div>
  )
}

// ── OverviewTab ───────────────────────────────────────────────────────────────

interface OverviewTabProps {
  doc: Document
  pipelineDurationMs: number | null | undefined
}

/**
 * Renders a two-column key/value grid of all available document metadata.
 *
 * Args:
 *   doc:                 Fully hydrated document record.
 *   pipelineDurationMs:  Pipeline wall-clock time cast from the raw response.
 */
function OverviewTab({ doc, pipelineDurationMs }: OverviewTabProps) {
  // 1. Build the list of rows from known document fields.
  const rows: Array<{ label: string; value: string }> = []

  const push = (label: string, value: string | null | undefined) => {
    if (value != null && value !== '') rows.push({ label, value })
  }

  push('ID', doc.id)
  push('Collection', doc.collection_id)
  push('Filename', doc.filename)
  push('Format', doc.format)
  push('File size', String(doc.file_size != null ? formatFileSize(doc.file_size) : null))
  push('Status', doc.status)
  push('Language', doc.language)
  push('Page count', doc.page_count != null ? String(doc.page_count) : null)
  push('Block count', doc.block_count != null ? String(doc.block_count) : null)
  push('Chunk count', doc.chunk_count != null ? String(doc.chunk_count) : null)
  push('Indexed', doc.indexed ? 'Yes' : 'No')
  push('Pipeline version', doc.pipeline_version)
  push('Pipeline duration', pipelineDurationMs != null ? formatDuration(pipelineDurationMs) : null)
  push('Quality score', doc.quality_score != null ? doc.quality_score.toFixed(3) : null)
  push('Source hash', doc.source_hash)
  push('Created at', doc.created_at ? new Date(doc.created_at).toLocaleString() : null)
  push('Has original', doc.has_original ? 'Yes' : 'No')
  push('Has markdown', doc.has_markdown ? 'Yes' : 'No')
  push('Has PDF', doc.has_pdf ? 'Yes' : 'No')

  // 2. Append any user_meta fields.
  if (doc.user_meta && typeof doc.user_meta === 'object') {
    for (const [k, v] of Object.entries(doc.user_meta)) {
      if (v != null) push(`user_meta.${k}`, String(v))
    }
  }

  // 3. Append any implicit_meta fields.
  if (doc.implicit_meta && typeof doc.implicit_meta === 'object') {
    for (const [k, v] of Object.entries(doc.implicit_meta)) {
      if (v != null) push(`implicit_meta.${k}`, String(v))
    }
  }

  // 4. Show pipeline errors if any.
  const errors = doc.pipeline_errors ?? []

  return (
    <div>
      {/* Metadata grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: '4px 16px', padding: '4px 0' }}>
        {rows.map(({ label, value }) => (
          <div key={label} style={{ display: 'contents' }}>
            <span className="stage-panel-label" style={{ minWidth: 180 }}>{label}</span>
            <span className="stage-panel-value mono" style={{ wordBreak: 'break-all', fontSize: 12 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Pipeline errors */}
      {errors.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="stage-panel-label" style={{ marginBottom: 6 }}>Pipeline errors</div>
          {errors.map((e, i) => (
            <div key={i} className="error-banner" style={{ marginBottom: 4, fontSize: 11 }}>{e}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── PagesTab ──────────────────────────────────────────────────────────────────

interface PagesTabProps {
  collectionId: string
  docId: string
  doc: Document
}

/**
 * Renders a thumbnail grid of document pages. Clicking a thumbnail loads
 * the full page detail (screenshot + block list).
 *
 * Args:
 *   collectionId: Collection identifier for API calls.
 *   docId:        Document identifier for API calls.
 *   doc:          Document record (used for status guard).
 */
function PagesTab({ collectionId, docId, doc }: PagesTabProps) {
  const [pages, setPages]             = useState<PageInfo[]>([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState<string | null>(null)
  const [selectedPage, setSelectedPage] = useState<number | null>(null)
  const [pageDetail, setPageDetail]   = useState<PageDetailResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // 1. Fetch page list when the document is done.
  useEffect(() => {
    if (doc.status !== 'done') return
    setLoading(true)
    listPages(collectionId, docId)
      .then(res => setPages(res.pages))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))
  }, [collectionId, docId, doc.status])

  // 2. Fetch page detail when a page is selected.
  useEffect(() => {
    if (selectedPage == null) { setPageDetail(null); return }
    setDetailLoading(true)
    getPage(collectionId, docId, selectedPage)
      .then(setPageDetail)
      .catch(() => setPageDetail(null))
      .finally(() => setDetailLoading(false))
  }, [collectionId, docId, selectedPage])

  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12 }}>
        {doc.status === 'running' || doc.status === 'pending'
          ? 'Processing in progress…'
          : 'No pages available.'}
      </div>
    )
  }

  if (loading) {
    return <div className="text-muted"><span className="spin">⟳</span> Loading pages…</div>
  }

  if (error) {
    return <div className="error-banner">{error}</div>
  }

  return (
    <div>
      {/* Thumbnail grid */}
      <div className="pages-grid" style={{ marginBottom: selectedPage != null ? 16 : 0 }}>
        {pages.map(page => (
          <div
            key={page.page}
            className={`page-thumb ${selectedPage === page.page ? 'page-thumb-selected' : ''}`}
            onClick={() => setSelectedPage(selectedPage === page.page ? null : page.page)}
            title={`Page ${page.page + 1} — ${page.n_blocks} blocks`}
          >
            <img
              src={getPageScreenshotUrl(collectionId, docId, page.page)}
              alt={`Page ${page.page + 1}`}
              loading="lazy"
            />
            <div style={{ padding: '3px 6px', fontSize: 10, color: 'var(--text-dim)', textAlign: 'center' }}>
              p.{page.page + 1}
            </div>
          </div>
        ))}
      </div>

      {/* Expanded page detail */}
      {selectedPage != null && (
        <div className="fadein" style={{
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          background: 'var(--surface-raised)',
          padding: 12,
          marginTop: 8,
        }}>
          {/* Large screenshot */}
          <div style={{ marginBottom: 12 }}>
            <img
              src={getPageScreenshotUrl(collectionId, docId, selectedPage)}
              alt={`Page ${selectedPage + 1}`}
              style={{ maxWidth: '100%', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)', display: 'block' }}
            />
          </div>

          {/* Block list */}
          {detailLoading ? (
            <div className="text-muted" style={{ fontSize: 12 }}>
              <span className="spin">⟳</span> Loading blocks…
            </div>
          ) : pageDetail ? (
            <div>
              <div className="stage-panel-label" style={{ marginBottom: 8 }}>
                {pageDetail.blocks.length} blocks on page {selectedPage + 1}
              </div>
              {pageDetail.blocks.map(block => (
                <div key={block.id} className="block-row" style={{ borderBottom: '1px solid var(--border)', padding: '5px 0', fontSize: 11 }}>
                  <span className="block-type-badge" style={{ marginRight: 8 }}>{block.type}</span>
                  <span className="mono text-dim" style={{ fontSize: 10 }}>{block.id.slice(0, 22)}…</span>
                  {block.text && (
                    <span className="text-muted" style={{ marginLeft: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                      {block.text.slice(0, 120)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

// ── DownloadsTab ──────────────────────────────────────────────────────────────

interface DownloadsTabProps {
  collectionId: string
  docId: string
  doc: Document
}

interface DownloadButtonProps {
  label: string
  icon: string
  available: boolean
  fetchUrl: () => Promise<PresignedUrlResponse>
}

/**
 * A download action button that fetches a presigned URL on click, then opens
 * it in a new tab. Shows a loading spinner during fetch and an error on failure.
 *
 * Args:
 *   label:    Human-readable label for the button.
 *   icon:     Emoji or text icon shown to the left of the label.
 *   available: Whether the file exists (guards against API errors for missing files).
 *   fetchUrl: Async function that resolves a PresignedUrlResponse.
 */
function DownloadButton({ label, icon, available, fetchUrl }: DownloadButtonProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  /**
   * Fetches the presigned URL and opens it in a new tab.
   */
  async function handleClick() {
    // 1. Guard: nothing to download if unavailable.
    if (!available || loading) return

    // 2. Fetch the URL and open it.
    setLoading(true)
    setError(null)
    try {
      const { url } = await fetchUrl()
      window.open(url, '_blank')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <button
        type="button"
        className="doc-download-btn"
        disabled={!available || loading}
        onClick={handleClick}
      >
        <span style={{ fontSize: 18 }}>{icon}</span>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{label}</span>
          {!available && (
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>
              Not available yet — process the document first
            </span>
          )}
        </div>
        {loading && <span className="spin" style={{ marginLeft: 'auto', color: 'var(--text-dim)' }}>⟳</span>}
        {!loading && available && (
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 12 }}>↓</span>
        )}
      </button>
      {error && (
        <div className="error-banner" style={{ marginTop: 4, fontSize: 11 }}>{error}</div>
      )}
    </div>
  )
}

/**
 * Renders the Downloads tab with three presigned-URL download buttons for the
 * document's original file, generated markdown, and generated PDF.
 *
 * Args:
 *   collectionId: Collection identifier forwarded to API calls.
 *   docId:        Document identifier forwarded to API calls.
 *   doc:          Document record — used to check availability flags.
 */
function DownloadsTab({ collectionId, docId, doc }: DownloadsTabProps) {
  return (
    <div className="doc-detail-downloads">
      <DownloadButton
        label="Original file"
        icon="📄"
        available={doc.has_original}
        fetchUrl={() => getDocumentOriginal(collectionId, docId)}
      />
      <DownloadButton
        label="Markdown"
        icon="📝"
        available={doc.has_markdown}
        fetchUrl={() => getDocumentMarkdown(collectionId, docId)}
      />
      <DownloadButton
        label="PDF"
        icon="🗒️"
        available={doc.has_pdf}
        fetchUrl={() => getDocumentPdf(collectionId, docId)}
      />
    </div>
  )
}

export default DocDetailView
