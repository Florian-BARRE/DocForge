// ====== Code Summary ======
// DocDetailView renders a full-screen detail view for a single document.
// Provides sub-tab navigation across: Overview, IR, Chunks, Pages, Downloads,
// Chain traces, Jobs, and In-doc search.  Owns the jumpChunkId signal used to
// cross-navigate from search results to the Chunks tab.
// Orchestration only — each sub-tab lives in ./detail/.

// ====== Standard Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getDocument } from '../../api/client'
import type { Document } from '../../api/types'

// ====== Local Project Imports ======
import { ChainTracesTab } from './detail/ChainTracesTab'
import { ChunksTab } from './detail/ChunksTab'
import { dotClass, formatFileSize, statusColor } from './detail/detailHelpers'
import { DownloadsTab } from './detail/DownloadsTab'
import { InDocSearch } from './detail/InDocSearch'
import { IRTab } from './detail/IRTab'
import { JobsTab } from './detail/JobsTab'
import { OverviewTab } from './detail/OverviewTab'
import { PagesTab } from './detail/PagesTab'

// ── Types ─────────────────────────────────────────────────────────────────────

type DetailTab = 'overview' | 'ir' | 'chunks' | 'pages' | 'downloads' | 'traces' | 'jobs' | 'search'

interface DocDetailViewProps {
  /** Collection the document belongs to. */
  collectionId: string
  /** UUID of the document to display. */
  docId: string
  /** Callback to return to the document list. */
  onBack: () => void
  /** When false, write-only controls (chunk edit) are hidden. */
  canWrite?: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * DocDetailView is a full-screen document inspector with eight sub-tabs.
 *
 * Fetches the document on mount, then renders:
 *   - Overview:      metadata grid + stale_reasons + pipeline_errors
 *   - IR:            per-page block inspector
 *   - Chunks:        full chunk browser (jumpChunkId-aware, canWrite-gated edit)
 *   - Pages:         screenshot thumbnails with block bbox overlays
 *   - Downloads:     presigned URL buttons
 *   - Chain traces:  parse + embed stage provenance
 *   - Jobs:          full job history
 *   - Search:        in-document search → jump-to-chunk cross-navigation
 *
 * Args:
 *   collectionId: UUID of the owning collection.
 *   docId:        UUID of the document to display.
 *   onBack:       Callback to navigate back to the document list.
 *   canWrite:     When false, write-only controls are hidden (default true).
 */
export function DocDetailView({ collectionId, docId, onBack, canWrite = true }: DocDetailViewProps) {
  // ── State ──────────────────────────────────────────────────────────────
  const [doc, setDoc]             = useState<Document | null>(null)
  const [activeTab, setActiveTab] = useState<DetailTab>('overview')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError]         = useState<string | null>(null)
  // chunkId to auto-open in ChunksTab after navigation from in-doc search.
  const [jumpChunkId, setJumpChunkId] = useState<string | null>(null)

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

  // 2. Jump from in-doc search: switch to Chunks tab and set the target chunk.
  function handleJumpToChunk(chunkId: string) {
    setJumpChunkId(chunkId)
    setActiveTab('chunks')
  }

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
          {doc.stale && (
            <span
              className="tag"
              style={{
                color: 'var(--s-warning)',
                borderColor: 'rgba(245,158,11,0.4)',
                background: 'rgba(245,158,11,0.1)',
              }}
            >
              stale
            </span>
          )}
        </div>
      </div>

      {/* ── Sub-tab navigation ── */}
      <div className="doc-detail-tabs">
        {(
          [
            { id: 'overview',  label: 'Overview' },
            { id: 'ir',        label: 'IR' },
            { id: 'chunks',    label: 'Chunks' },
            { id: 'pages',     label: 'Pages' },
            { id: 'downloads', label: 'Downloads' },
            { id: 'traces',    label: 'Chain traces' },
            { id: 'jobs',      label: 'Jobs' },
            { id: 'search',    label: 'Search' },
          ] as { id: DetailTab; label: string }[]
        ).map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className={`doc-detail-tab ${activeTab === id ? 'doc-detail-tab-active' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Tab body ── */}
      <div className="doc-detail-body">
        {activeTab === 'overview' && (
          <OverviewTab doc={doc} pipelineDurationMs={pipelineDurationMs} />
        )}
        {activeTab === 'ir' && (
          <IRTab doc={doc} collectionId={collectionId} />
        )}
        {activeTab === 'chunks' && (
          <ChunksTab
            doc={doc}
            collectionId={collectionId}
            jumpChunkId={jumpChunkId}
            canWrite={canWrite}
          />
        )}
        {activeTab === 'pages' && (
          <PagesTab collectionId={collectionId} docId={docId} doc={doc} />
        )}
        {activeTab === 'downloads' && (
          <DownloadsTab collectionId={collectionId} docId={docId} doc={doc} />
        )}
        {activeTab === 'traces' && (
          <ChainTracesTab doc={doc} />
        )}
        {activeTab === 'jobs' && (
          <JobsTab doc={doc} />
        )}
        {activeTab === 'search' && (
          <InDocSearch
            collectionId={collectionId}
            docId={docId}
            onJumpToChunk={handleJumpToChunk}
          />
        )}
      </div>
    </div>
  )
}

export default DocDetailView
