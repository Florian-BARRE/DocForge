// ====== Code Summary ======
// Browse mode — two-column layout: collection list on the left, document list on the right.
// Each document row has an "Inspect" button that switches to the Inspect tab.

import { useState, useEffect } from 'react'
import type { Collection, Document } from '../../api/types'
import { listCollections, listDocuments } from '../../api/client'

interface Props {
  // Called when user clicks "Inspect" on a document — parent switches to Inspect tab.
  onInspect: (collection: Collection, doc: Document) => void
}

function statusColor(s: string) {
  if (s === 'done') return 'var(--s-done)'
  if (s === 'error') return 'var(--s-error)'
  if (s === 'running') return 'var(--s-running)'
  return 'var(--text-dim)'
}

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Collection browse view with split-pane layout.
 * Left: collection list. Right: documents for selected collection.
 */
export function BrowseView({ onInspect }: Props) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [collectionsLoading, setCollectionsLoading] = useState(true)
  const [collectionsError, setCollectionsError] = useState<string | null>(null)
  const [selectedCollection, setSelectedCollection] = useState<Collection | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [docsTotal, setDocsTotal] = useState(0)
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const PAGE_SIZE = 50

  // 1. Load collections on mount.
  useEffect(() => {
    void loadCollections()
  }, [])

  async function loadCollections() {
    setCollectionsLoading(true)
    setCollectionsError(null)
    try {
      const res = await listCollections()
      setCollections(res.collections)
      if (res.collections.length > 0) {
        setSelectedCollection(res.collections[0])
      }
    } catch (err) {
      setCollectionsError(String(err))
    } finally {
      setCollectionsLoading(false)
    }
  }

  // 2. Load documents when collection changes.
  useEffect(() => {
    if (selectedCollection) {
      setOffset(0)
      void loadDocs(selectedCollection.id, 0)
    }
  }, [selectedCollection?.id])

  async function loadDocs(collectionId: string, off: number) {
    setDocsLoading(true)
    setDocsError(null)
    try {
      const res = await listDocuments(collectionId, { limit: PAGE_SIZE, offset: off })
      setDocs(res.documents)
      setDocsTotal(res.total)
    } catch (err) {
      setDocsError(String(err))
    } finally {
      setDocsLoading(false)
    }
  }

  function selectCollection(col: Collection) {
    setSelectedCollection(col)
    setDocs([])
  }

  function prevPage() {
    const newOff = Math.max(0, offset - PAGE_SIZE)
    setOffset(newOff)
    if (selectedCollection) void loadDocs(selectedCollection.id, newOff)
  }

  function nextPage() {
    const newOff = offset + PAGE_SIZE
    if (newOff < docsTotal) {
      setOffset(newOff)
      if (selectedCollection) void loadDocs(selectedCollection.id, newOff)
    }
  }

  return (
    <div className="browse-layout">
      {/* Left sidebar — collection list */}
      <div className="browse-sidebar">
        <div className="browse-sidebar-header">
          Collections
          {!collectionsLoading && (
            <span className="text-dim" style={{ marginLeft: 8 }}>({collections.length})</span>
          )}
        </div>
        <div className="browse-sidebar-list">
          {collectionsLoading && (
            <div className="text-muted" style={{ padding: '8px 10px' }}>
              <span className="spin">⟳</span> Loading…
            </div>
          )}
          {collectionsError && (
            <div className="error-banner" style={{ margin: 6 }}>{collectionsError}</div>
          )}
          {collections.map(col => (
            <div
              key={col.id}
              className={`browse-col-item ${col.id === selectedCollection?.id ? 'browse-col-item-active' : ''}`}
              onClick={() => selectCollection(col)}
            >
              <span className="browse-col-name">{col.name}</span>
            </div>
          ))}
          {!collectionsLoading && collections.length === 0 && (
            <div className="text-dim" style={{ padding: '8px 10px', fontSize: 12 }}>
              No collections.
            </div>
          )}
        </div>
      </div>

      {/* Right main — document list */}
      <div className="browse-main">
        {!selectedCollection ? (
          <div className="empty">
            <div className="empty-icon">📂</div>
            <div>Select a collection to browse its documents.</div>
          </div>
        ) : (
          <>
            <div className="panel-header" style={{ marginBottom: 16 }}>
              <div className="panel-title">{selectedCollection.name}</div>
              <div className="panel-meta text-muted">
                <span>{docsTotal} documents</span>
                <span className="mono" style={{ fontSize: 11 }}>{selectedCollection.pipeline_version}</span>
              </div>
            </div>

            {docsError && <div className="error-banner">{docsError}</div>}

            {docsLoading ? (
              <div className="text-muted"><span className="spin">⟳</span> Loading documents…</div>
            ) : docs.length === 0 ? (
              <div className="empty" style={{ padding: '32px 0' }}>
                <div className="empty-icon">📄</div>
                <div>No documents in this collection.</div>
              </div>
            ) : (
              <div className="doc-list">
                {docs.map(doc => (
                  <div key={doc.id} className="doc-row">
                    {/* Status dot */}
                    <span
                      className="dot"
                      style={{ background: statusColor(doc.status) }}
                    />
                    {/* Filename */}
                    <span className="doc-name">{doc.filename}</span>
                    {/* Format */}
                    <span className="doc-meta text-muted">{doc.format.toUpperCase()}</span>
                    {/* Size */}
                    <span className="doc-meta text-dim">{fmtBytes(doc.file_size)}</span>
                    {/* Pages */}
                    {doc.page_count != null && (
                      <span className="doc-meta text-dim">{doc.page_count} pp</span>
                    )}
                    {/* Chunks */}
                    {doc.chunk_count != null && (
                      <span className="doc-meta text-dim">{doc.chunk_count} chunks</span>
                    )}
                    {/* Status tag */}
                    <span
                      className="tag"
                      style={{
                        color: statusColor(doc.status),
                        borderColor: statusColor(doc.status) + '40',
                        background: statusColor(doc.status) + '10',
                        flexShrink: 0,
                      }}
                    >
                      {doc.status === 'running' && <span className="spin" style={{ fontSize: 9 }}>⟳</span>}
                      {doc.status}
                    </span>
                    {/* Inspect button */}
                    <div className="doc-actions" style={{ opacity: 1 }}>
                      <button
                        type="button"
                        className="btn btn-ghost"
                        style={{ fontSize: 11, padding: '2px 8px' }}
                        onClick={() => onInspect(selectedCollection, doc)}
                      >
                        Inspect →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {docsTotal > PAGE_SIZE && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={offset === 0}
                  onClick={prevPage}
                >← Prev</button>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, docsTotal)} of {docsTotal}
                </span>
                <button
                  type="button"
                  className="btn"
                  disabled={offset + PAGE_SIZE >= docsTotal}
                  onClick={nextPage}
                >Next →</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
