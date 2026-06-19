// ====== Code Summary ======
// Browse mode — split-pane: collection list on the left, document list on the right.
// The query controls (status filter, sort_by, sort_order, limit, offset) come straight
// from list_documents's OpenAPI query_params via <RequestForm>, so any new query param
// added server-side surfaces here automatically.

import { useState, useEffect, useMemo } from 'react'
import type {
  Collection, DiscoveryResponse, Document, EndpointDescriptor,
} from '../../api/types'
import { listCollections, listDocuments, getDiscovery } from '../../api/client'
import { RequestForm } from '../ui/RequestForm'

interface Props {
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

const DEFAULT_LIMIT = 50

export function BrowseView({ onInspect }: Props) {
  const [collections, setCollections] = useState<Collection[]>([])
  const [collectionsLoading, setCollectionsLoading] = useState(true)
  const [collectionsError, setCollectionsError] = useState<string | null>(null)
  const [selectedCollection, setSelectedCollection] = useState<Collection | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [docsTotal, setDocsTotal] = useState(0)
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState<string | null>(null)
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)
  // Query state owned here; query_params come from discovery via RequestForm.
  const [query, setQuery] = useState<Record<string, unknown>>({ limit: DEFAULT_LIMIT, offset: 0 })

  // 1. Load collections + unscoped discovery on mount.
  useEffect(() => {
    void loadCollections()
    void loadDiscovery()
  }, [])

  async function loadCollections() {
    setCollectionsLoading(true)
    setCollectionsError(null)
    try {
      const res = await listCollections()
      setCollections(res.collections)
      if (res.collections.length > 0) setSelectedCollection(res.collections[0])
    } catch (err) {
      setCollectionsError(String(err))
    } finally {
      setCollectionsLoading(false)
    }
  }

  async function loadDiscovery() {
    try {
      setDiscovery(await getDiscovery())
    } catch { /* non-critical */ }
  }

  const listEndpoint: EndpointDescriptor | undefined = useMemo(
    () => discovery?.endpoints.find(e => e.route_name === 'list_documents'),
    [discovery],
  )

  // 2. Reload docs whenever the selected collection or query knobs change.
  useEffect(() => {
    if (!selectedCollection) return
    void loadDocs(selectedCollection.id, query)
  }, [selectedCollection?.id, JSON.stringify(query)])

  async function loadDocs(collectionId: string, q: Record<string, unknown>) {
    setDocsLoading(true)
    setDocsError(null)
    try {
      const res = await listDocuments(collectionId, {
        limit:      typeof q.limit  === 'number' ? (q.limit  as number) : undefined,
        offset:     typeof q.offset === 'number' ? (q.offset as number) : undefined,
        status:     typeof q.status === 'string' ? (q.status as string) : undefined,
        sort_by:    typeof q.sort_by === 'string' ? (q.sort_by as string) : undefined,
        sort_order: q.sort_order === 'asc' || q.sort_order === 'desc'
          ? (q.sort_order as 'asc' | 'desc') : undefined,
      })
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
    setQuery(prev => ({ ...prev, offset: 0 }))
    setDocs([])
  }

  function prevPage() {
    const current = typeof query.offset === 'number' ? (query.offset as number) : 0
    const limit = typeof query.limit === 'number' ? (query.limit as number) : DEFAULT_LIMIT
    setQuery(prev => ({ ...prev, offset: Math.max(0, current - limit) }))
  }

  function nextPage() {
    const current = typeof query.offset === 'number' ? (query.offset as number) : 0
    const limit = typeof query.limit === 'number' ? (query.limit as number) : DEFAULT_LIMIT
    if (current + limit < docsTotal) {
      setQuery(prev => ({ ...prev, offset: current + limit }))
    }
  }

  const offset = typeof query.offset === 'number' ? (query.offset as number) : 0
  const limit  = typeof query.limit  === 'number' ? (query.limit  as number) : DEFAULT_LIMIT

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

            {/* Discovery-driven query controls */}
            {listEndpoint && discovery && (
              <RequestForm
                endpoint={listEndpoint}
                discovery={discovery}
                body={{}}
                query={query}
                onBodyChange={() => {}}
                onQueryChange={setQuery}
              />
            )}

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
                    <span className="dot" style={{ background: statusColor(doc.status) }} />
                    <span className="doc-name">{doc.filename}</span>
                    <span className="doc-meta text-muted">{doc.format.toUpperCase()}</span>
                    <span className="doc-meta text-dim">{fmtBytes(doc.file_size)}</span>
                    {doc.page_count != null && (
                      <span className="doc-meta text-dim">{doc.page_count} pp</span>
                    )}
                    {doc.chunk_count != null && (
                      <span className="doc-meta text-dim">{doc.chunk_count} chunks</span>
                    )}
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

            {docsTotal > limit && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={offset === 0}
                  onClick={prevPage}
                >← Prev</button>
                <span className="text-muted" style={{ fontSize: 12 }}>
                  {offset + 1}–{Math.min(offset + limit, docsTotal)} of {docsTotal}
                </span>
                <button
                  type="button"
                  className="btn"
                  disabled={offset + limit >= docsTotal}
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
