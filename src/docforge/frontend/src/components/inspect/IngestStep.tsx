// ====== Code Summary ======
// Step 3 of Inspect mode — file drop-zone + discovery-driven body form + status polling.
// The dropzone owns the `file` part (multipart binary); everything else (the `metadata`
// overlay declared by /api/v1/discovery for ingest_document) is rendered by <RequestForm>.

import { useState, useEffect, useRef, useCallback } from 'react'
import type {
  Collection, DiscoveryResponse, Document, EndpointDescriptor,
} from '../../api/types'
import { listDocuments, ingestDocument, getDocument, getDiscovery } from '../../api/client'
import { RequestForm } from '../ui/RequestForm'

interface Props {
  collection: Collection
  onIngested: (doc: Document) => void
}

/**
 * Multipart ingest step.
 *
 * Body is constructed as:
 *   • `file` → from the dropzone
 *   • everything else (metadata overlay, any new field added server-side) → from
 *     <RequestForm body=…> which iterates the input schema + dynamic_fields verbatim.
 */
export function IngestStep({ collection, onIngested }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [body, setBody] = useState<Record<string, unknown>>({})
  const [ingesting, setIngesting] = useState(false)
  const [ingestError, setIngestError] = useState<string | null>(null)
  const [pollingDocId, setPollingDocId] = useState<string | null>(null)
  const [pollingStatus, setPollingStatus] = useState<string>('')
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)
  const [docs, setDocs] = useState<Document[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 1. Load existing docs + scoped discovery on mount.
  useEffect(() => {
    void loadDocs()
    void loadDiscovery()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [collection.id])

  async function loadDocs() {
    setDocsLoading(true)
    try {
      const res = await listDocuments(collection.id, { limit: 50 })
      setDocs(res.documents)
    } catch { /* ignore */ }
    finally { setDocsLoading(false) }
  }

  async function loadDiscovery() {
    try {
      setDiscovery(await getDiscovery(collection.id))
    } catch { /* non-critical */ }
  }

  // 2. Locate the ingest endpoint.
  const ingestEndpoint: EndpointDescriptor | undefined = discovery?.endpoints.find(
    e => e.route_name === 'ingest_document',
  )

  // 3. Poll getDocument until terminal status.
  const startPolling = useCallback((docId: string) => {
    setPollingDocId(docId)
    setPollingStatus('pending')
    pollRef.current = setInterval(async () => {
      try {
        const doc = await getDocument(collection.id, docId)
        setPollingStatus(doc.status)
        if (doc.status === 'done' || doc.status === 'error') {
          if (pollRef.current) clearInterval(pollRef.current)
          setPollingDocId(null)
          setIngesting(false)
          void loadDocs()
          onIngested(doc)
        }
      } catch { /* keep polling */ }
    }, 2000)
  }, [collection.id, onIngested])

  // 4. Drag-and-drop handlers.
  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files[0]
    if (dropped) setFile(dropped)
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0]
    if (picked) setFile(picked)
  }

  // 5. Submit ingest.  The metadata body field is built by RequestForm via the
  // metadata_write overlay; the api client encodes it as a JSON string for multipart.
  async function handleIngest() {
    if (!file) return
    setIngesting(true)
    setIngestError(null)
    try {
      const metadata = (body.metadata as Record<string, unknown> | undefined) ?? undefined
      const cleanMeta = metadata && Object.keys(metadata).length > 0 ? metadata : undefined
      const res = await ingestDocument(collection.id, file, cleanMeta)
      setFile(null)
      setBody({})
      startPolling(res.doc_id)
    } catch (err) {
      setIngestError(String(err))
      setIngesting(false)
    }
  }

  const statusColor = (s: string) => {
    if (s === 'done') return 'var(--s-done)'
    if (s === 'error') return 'var(--s-error)'
    if (s === 'running') return 'var(--s-running)'
    return 'var(--text-muted)'
  }

  const statusLabel = (s: Document['status']) => {
    if (s === 'done') return '✓ done'
    if (s === 'error') return '✗ error'
    if (s === 'running') return '⟳ running'
    return '· pending'
  }

  return (
    <div className="panel fadein">
      <div className="panel-header">
        <div className="panel-title">Ingest document</div>
      </div>

      {/* Drop zone — owns the `file` body field */}
      <div
        className={`dropzone ${dragOver ? 'dropzone-active' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        {file ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>{file.name}</span>
            <span className="text-muted" style={{ fontSize: 11 }}>
              ({(file.size / 1024 / 1024).toFixed(1)} MB)
            </span>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 11, padding: '2px 6px' }}
              onClick={e => { e.stopPropagation(); setFile(null) }}
            >✕</button>
          </div>
        ) : (
          <div className="dropzone-placeholder">
            <span className="dropzone-icon">⬆</span>
            <span>Drop a file here or click to browse</span>
            <span className="text-dim" style={{ fontSize: 11 }}>
              {collection.supported_formats.join(', ')}
            </span>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
      </div>

      {/* Discovery-driven body form — picks up the metadata overlay and any future field. */}
      {ingestEndpoint && discovery && (
        <div style={{ marginTop: 14 }}>
          <RequestForm
            endpoint={ingestEndpoint}
            discovery={discovery}
            body={body}
            query={{}}
            onBodyChange={setBody}
            onQueryChange={() => {}}
            excludeBodyFields={['file']}
          />
        </div>
      )}

      {ingestError && <div className="error-banner">{ingestError}</div>}

      {pollingDocId && (
        <div className="info-banner" style={{ marginTop: 10 }}>
          <span className="spin">⟳</span>
          Processing… status: <span style={{ color: statusColor(pollingStatus) }}>{pollingStatus}</span>
        </div>
      )}

      <div className="row-end" style={{ marginTop: 14 }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!file || ingesting}
          onClick={handleIngest}
        >
          {ingesting ? <span className="spin">⟳</span> : null}
          {ingesting ? ' Ingesting…' : 'Ingest'}
        </button>
      </div>

      {/* Existing documents list */}
      <div className="section">
        <div className="section-title-row">
          <div className="section-title">Existing documents</div>
          <button
            type="button"
            className="btn btn-ghost"
            style={{ fontSize: 11 }}
            onClick={loadDocs}
          >↻ Refresh</button>
        </div>
        {docsLoading ? (
          <div className="text-muted"><span className="spin">⟳</span> Loading…</div>
        ) : docs.length === 0 ? (
          <div className="empty" style={{ padding: '20px 0' }}>
            <div className="text-dim">No documents yet.</div>
          </div>
        ) : (
          <div className="doc-list">
            {docs.map(doc => (
              <div
                key={doc.id}
                className="doc-row doc-row-clickable"
                onClick={() => onIngested(doc)}
                title="Click to inspect this document"
              >
                <span
                  className="dot"
                  style={{
                    background: doc.status === 'done' ? 'var(--s-done)'
                      : doc.status === 'error' ? 'var(--s-error)'
                      : doc.status === 'running' ? 'var(--s-running)'
                      : 'var(--s-pending)',
                  }}
                />
                <span className="doc-name">{doc.filename}</span>
                <span className="doc-meta text-muted">
                  {doc.format}
                  {doc.page_count ? ` · ${doc.page_count} pp` : ''}
                </span>
                <span
                  className="doc-meta mono"
                  style={{ fontSize: 11, color: statusColor(doc.status) }}
                >
                  {statusLabel(doc.status)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
