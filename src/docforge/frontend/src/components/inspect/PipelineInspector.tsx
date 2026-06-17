// ====== Code Summary ======
// Step 4 of Inspect mode — full pipeline inspector for a selected document.
// Header: filename + status badges + download buttons + inline markdown viewer toggle.
// Body: S0/S1/S2/S45/S6 stage blocks. Polls while pending/running.

import { useState, useEffect, useRef, useCallback } from 'react'
import type { Collection, Document } from '../../api/types'
import {
  getDocument,
  getDocumentOriginal,
  getDocumentMarkdown,
  getDocumentPdf,
  getBlockFigure,
  reingestDocument,
} from '../../api/client'
import { S0Block } from './stages/S0Block'
import { S1Block } from './stages/S1Block'
import { S45Block } from './stages/S45Block'
import { S6Block } from './stages/S6Block'
import { StageBlock } from './stages/StageBlock'

interface Props {
  collection: Collection
  initialDoc: Document
  onBack: () => void
}

/**
 * Pipeline inspector — polls until terminal status, then renders all stage blocks.
 * Includes an inline IR Markdown viewer that fetches the presigned URL on demand.
 */
export function PipelineInspector({ collection, initialDoc, onBack }: Props) {
  const [doc, setDoc]                       = useState<Document>(initialDoc)
  const [downloading, setDownloading]       = useState<string | null>(null)
  const [reingesting, setReingesting]       = useState(false)
  const [error, setError]                   = useState<string | null>(null)
  const [markdownText, setMarkdownText]     = useState<string | null>(null)
  const [markdownFigures, setMarkdownFigures] = useState<Record<string, string>>({})
  const [showMarkdown, setShowMarkdown]     = useState(false)
  const [loadingMarkdown, setLoadingMarkdown] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  // 1. Sync with latest initialDoc when it changes.
  useEffect(() => {
    setDoc(initialDoc)
  }, [initialDoc.id])

  // 2. Auto-poll while running / pending.
  useEffect(() => {
    if (doc.status === 'running' || doc.status === 'pending') {
      stopPoll()
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getDocument(collection.id, doc.id)
          setDoc(updated)
          if (updated.status !== 'running' && updated.status !== 'pending') stopPoll()
        } catch { /* keep polling */ }
      }, 2000)
    } else {
      stopPoll()
    }
    return stopPoll
  }, [doc.id, doc.status, collection.id, stopPoll])

  // 3. Download / open in new tab.
  async function handleDownload(kind: 'original' | 'pdf' | 'markdown') {
    setDownloading(kind)
    setError(null)
    try {
      let res
      if (kind === 'original') res = await getDocumentOriginal(collection.id, doc.id)
      else if (kind === 'pdf') res = await getDocumentPdf(collection.id, doc.id)
      else res = await getDocumentMarkdown(collection.id, doc.id)
      window.open(res.url, '_blank')
    } catch (err) {
      setError(String(err))
    } finally {
      setDownloading(null)
    }
  }

  // 4. Inline markdown viewer — fetch content once, resolve figure refs, toggle display.
  async function handleViewMarkdown() {
    if (showMarkdown) { setShowMarkdown(false); return }
    if (markdownText)  { setShowMarkdown(true);  return }
    setLoadingMarkdown(true)
    setError(null)
    try {
      const { url } = await getDocumentMarkdown(collection.id, doc.id)
      const resp = await fetch(url)
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const text = await resp.text()
      setMarkdownText(text)

      // Resolve figure refs: our serializer emits ![fig:{blockId}](fig:{blockId})
      const FIG_RE = /!\[fig:([^\]]+)\]\(fig:[^\)]+\)/g
      const blockIds = [...new Set([...text.matchAll(FIG_RE)].map(m => m[1]))]
      const urls: Record<string, string> = {}
      await Promise.allSettled(
        blockIds.map(async (blockId) => {
          try {
            const r = await getBlockFigure(collection.id, doc.id, blockId)
            urls[blockId] = r.url
          } catch { /* crop not ready yet */ }
        })
      )
      setMarkdownFigures(urls)
      setShowMarkdown(true)
    } catch (err) {
      setError(`Markdown viewer: ${String(err)}`)
    } finally {
      setLoadingMarkdown(false)
    }
  }

  // 5. Re-ingest.
  async function handleReingest() {
    if (!confirm('Re-ingest this document? Existing chunks and index entries will be replaced.')) return
    setReingesting(true)
    setError(null)
    try {
      await reingestDocument(collection.id, doc.id, true)
      const updated = await getDocument(collection.id, doc.id)
      setDoc(updated)
    } catch (err) {
      setError(String(err))
    } finally {
      setReingesting(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
      {/* ── Inspector header ── */}
      <div className="inspector-header">
        <button type="button" className="btn btn-ghost" onClick={onBack} style={{ flexShrink: 0 }}>
          ← Back
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="inspector-filename">{doc.filename}</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
            <StatusBadge status={doc.status} />
            {doc.page_count  != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.page_count} pp</span>}
            {doc.block_count != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.block_count} blocks</span>}
            {doc.chunk_count != null && <span className="text-dim" style={{ fontSize: 11 }}>{doc.chunk_count} chunks</span>}
            {doc.language               && <span className="text-dim" style={{ fontSize: 11 }}>{doc.language}</span>}
          </div>
        </div>

        {/* Action buttons */}
        <div className="inspector-downloads">
          {doc.has_original && (
            <button type="button" className="btn btn-ghost" style={{ fontSize: 11 }}
              disabled={downloading === 'original'} onClick={() => void handleDownload('original')}>
              {downloading === 'original' ? <span className="spin">⟳</span> : '↓'} Original
            </button>
          )}
          {doc.has_pdf && (
            <button type="button" className="btn btn-ghost" style={{ fontSize: 11 }}
              disabled={downloading === 'pdf'} onClick={() => void handleDownload('pdf')}>
              {downloading === 'pdf' ? <span className="spin">⟳</span> : '↓'} PDF
            </button>
          )}
          {doc.has_markdown && (
            <>
              <button type="button" className="btn btn-ghost" style={{ fontSize: 11 }}
                disabled={downloading === 'markdown'} onClick={() => void handleDownload('markdown')}>
                {downloading === 'markdown' ? <span className="spin">⟳</span> : '↓'} IR .md
              </button>
              <button
                type="button"
                className={`btn ${showMarkdown ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: 11 }}
                disabled={loadingMarkdown}
                onClick={() => void handleViewMarkdown()}
              >
                {loadingMarkdown ? <span className="spin">⟳</span> : '◎'} {showMarkdown ? 'Hide IR' : 'View IR'}
              </button>
            </>
          )}
          <button type="button" className="btn" style={{ fontSize: 11 }}
            disabled={reingesting} onClick={handleReingest}>
            {reingesting ? <span className="spin">⟳</span> : '↺'} Re-ingest
          </button>
        </div>
      </div>

      {error && (
        <div className="error-banner" style={{ margin: '8px 24px 0' }}>{error}</div>
      )}

      {/* ── Inline markdown viewer ── */}
      {showMarkdown && markdownText && (
        <div className="markdown-viewer fadein">
          <div className="markdown-viewer-header">
            <span>IR Markdown — {doc.filename}</span>
            <span className="text-dim" style={{ fontSize: 10 }}>
              {Object.keys(markdownFigures).length > 0
                ? `${Object.keys(markdownFigures).length} figure(s) resolved`
                : ''}
            </span>
            <button type="button" className="btn-icon" onClick={() => setShowMarkdown(false)}>✕</button>
          </div>
          <div className="markdown-content">
            <MarkdownRenderer text={markdownText} figureUrls={markdownFigures} />
          </div>
        </div>
      )}

      {/* ── Stage blocks ── */}
      <div className="inspector-scroll">
        <div style={{ padding: '16px 24px', maxWidth: 960, margin: '0 auto' }}>
          <S0Block doc={doc} collectionId={collection.id} />
          <S1Block doc={doc} collectionId={collection.id} />

          {/* S2 — Enrich: enrichment data is visible inline in each figure block above */}
          <StageBlock
            title="S2 — Enrich"
            status={doc.status === 'done' ? 'done' : doc.status === 'error' ? 'error' : doc.status === 'running' ? 'running' : 'pending'}
            defaultOpen={false}
          >
            <div className="text-muted" style={{ fontSize: 12 }}>
              OCR / VLM enrichment results are shown inline in each FIGURE block above (kind, relevance, ocr_text, description, data_table).
            </div>
          </StageBlock>

          <S45Block doc={doc} collectionId={collection.id} />
          <S6Block doc={doc} collectionId={collection.id} />
        </div>
      </div>
    </div>
  )
}

// ── Markdown renderer with inline figure images ───────────────────────────────

const FIG_LINE_RE = /^!\[fig:([^\]]+)\]\(fig:[^\)]+\)$/

interface MarkdownRendererProps {
  text: string
  figureUrls: Record<string, string>
}

function MarkdownRenderer({ text, figureUrls }: MarkdownRendererProps) {
  const lines = text.split('\n')
  return (
    <>
      {lines.map((line, i) => {
        const m = line.match(FIG_LINE_RE)
        if (m) {
          const blockId = m[1]
          const url = figureUrls[blockId]
          return url ? (
            <div key={i} className="ir-figure-wrap">
              <img src={url} alt={`fig:${blockId}`} className="ir-figure-img-inline" loading="lazy" />
              <span className="text-dim mono" style={{ fontSize: 9, display: 'block', marginTop: 2 }}>
                {blockId}
              </span>
            </div>
          ) : (
            <div key={i} className="ir-figure-placeholder">
              [figure: {blockId}]
            </div>
          )
        }
        // Regular markdown line — rendered as-is in monospace
        return <div key={i} className="markdown-line">{line || ' '}</div>
      })}
    </>
  )
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document['status'] }) {
  const color =
    status === 'done'    ? 'var(--s-done)'    :
    status === 'error'   ? 'var(--s-error)'   :
    status === 'running' ? 'var(--s-running)' :
    'var(--text-dim)'

  return (
    <span className="tag" style={{ color, borderColor: color + '40', background: color + '10' }}>
      {status === 'running' && <span className="spin" style={{ fontSize: 9 }}>⟳</span>}
      {status}
    </span>
  )
}
