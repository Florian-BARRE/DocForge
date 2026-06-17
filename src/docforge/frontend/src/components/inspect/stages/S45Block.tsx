// ====== Code Summary ======
// Stage S4/S5 block — shows chunks with their raw_text, embed_text, and provenance.
// Each chunk is collapsed by default; click to expand raw_text / embed_text tabs.

import { useState, useEffect } from 'react'
import type { Document, ChunkResponse } from '../../../api/types'
import { listChunks, getBlockFigure } from '../../../api/client'
import { StageBlock, docStatusToStage } from './StageBlock'

interface Props {
  doc: Document
  collectionId: string
}

/**
 * Chunk list for S4/S5 stages.
 * Loads up to 200 chunks on mount when doc is done.
 */
export function S45Block({ doc, collectionId }: Props) {
  const [chunks, setChunks] = useState<ChunkResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Set of expanded chunk ids.
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  // Active text tab per chunk: 'raw' | 'embed'
  const [textTab, setTextTab] = useState<Record<string, 'raw' | 'embed'>>({})

  // Presigned URL cache for figure chunks: chunkId → url
  const [figureSrcs, setFigureSrcs] = useState<Record<string, string>>({})

  const stageStatus = docStatusToStage(doc.status)

  useEffect(() => {
    if (doc.status === 'done') void loadChunks()
  }, [doc.id, doc.status])

  async function loadChunks() {
    setLoading(true)
    setError(null)
    try {
      const res = await listChunks(collectionId, doc.id, { limit: 200 })
      setChunks(res.chunks)
      setTotal(res.total)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
    }
  }

  async function fetchFigureSrc(chunk: ChunkResponse) {
    if (figureSrcs[chunk.id] !== undefined) return
    if (chunk.strategy !== 'figure' || chunk.block_ids.length === 0) return
    try {
      const r = await getBlockFigure(collectionId, doc.id, chunk.block_ids[0])
      setFigureSrcs(prev => ({ ...prev, [chunk.id]: r.url }))
    } catch {
      // Crop not available yet — store empty string to avoid retry on re-open
      setFigureSrcs(prev => ({ ...prev, [chunk.id]: '' }))
    }
  }

  function toggleChunk(id: string, chunk: ChunkResponse) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        void fetchFigureSrc(chunk)
      }
      return next
    })
  }

  function getTab(id: string): 'raw' | 'embed' {
    return textTab[id] ?? 'raw'
  }

  function setTab(id: string, tab: 'raw' | 'embed') {
    setTextTab(prev => ({ ...prev, [id]: tab }))
  }

  // Extract pages from prov object.
  function getPages(chunk: ChunkResponse): number[] {
    const prov = chunk.prov as Record<string, unknown>
    const pages = prov?.pages
    if (Array.isArray(pages)) return pages as number[]
    return []
  }

  function getHeadingPath(chunk: ChunkResponse): string | null {
    const prov = chunk.prov as Record<string, unknown>
    return typeof prov?.heading_path === 'string' ? prov.heading_path : null
  }

  const summary = doc.status === 'done'
    ? `${doc.chunk_count ?? total} chunks${chunks[0]?.strategy ? ` · ${chunks[0].strategy}` : ''}`
    : undefined

  return (
    <StageBlock
      title="S4/S5 — Chunks"
      summary={summary}
      status={stageStatus}
      defaultOpen={false}
    >
      {doc.status !== 'done' && (
        <div className="text-muted" style={{ fontSize: 12 }}>
          {doc.status === 'running' || doc.status === 'pending'
            ? 'Chunking in progress…'
            : 'No chunks.'}
        </div>
      )}

      {error && <div className="error-banner">{error}</div>}

      {loading && <div className="text-muted"><span className="spin">⟳</span> Loading chunks…</div>}

      {total > 200 && (
        <div className="info-banner">
          <span className="info-icon">ℹ</span>
          Showing first 200 of {total} chunks.
        </div>
      )}

      {chunks.length > 0 && (
        <div className="chunk-list">
          {chunks.map((chunk, idx) => {
            const isOpen = expanded.has(chunk.id)
            const pages = getPages(chunk)
            const headingPath = getHeadingPath(chunk)
            const tab = getTab(chunk.id)

            return (
              <div key={chunk.id} className={`chunk-card ${isOpen ? 'chunk-card-expanded' : ''}`}>
                <div className="chunk-header" onClick={() => toggleChunk(chunk.id, chunk)}>
                  <span className="chunk-rank text-dim mono">#{idx + 1}</span>
                  {pages.length > 0 && (
                    <span className="chunk-pages text-muted">
                      [p.{pages.join(',')}]
                    </span>
                  )}
                  <span className="chunk-strategy">{chunk.strategy}</span>
                  <span className="chunk-tok text-dim">{chunk.token_count} tok</span>
                  <span className="chunk-preview text-muted">
                    {chunk.raw_text.slice(0, 120)}
                  </span>
                  <span className="chunk-toggle text-dim">{isOpen ? '▲' : '▼'}</span>
                </div>

                {isOpen && (
                  <div className="chunk-detail fadein">
                    {headingPath && (
                      <div className="chunk-breadcrumb mono">
                        {headingPath}
                      </div>
                    )}

                    {/* Figure crop image for figure-strategy chunks */}
                    {chunk.strategy === 'figure' && (
                      <div className="chunk-figure-preview">
                        {figureSrcs[chunk.id] ? (
                          <img
                            src={figureSrcs[chunk.id]}
                            alt="Figure crop"
                            className="figure-crop-img"
                            loading="lazy"
                          />
                        ) : figureSrcs[chunk.id] === '' ? (
                          <span className="text-dim" style={{ fontSize: 10 }}>crop not available</span>
                        ) : (
                          <span className="text-dim" style={{ fontSize: 10 }}><span className="spin">⟳</span> loading…</span>
                        )}
                      </div>
                    )}

                    <div className="chunk-text-tabs">
                      <button
                        type="button"
                        className={`chunk-text-tab ${tab === 'raw' ? 'chunk-text-tab-active' : ''}`}
                        onClick={() => setTab(chunk.id, 'raw')}
                      >
                        raw_text
                      </button>
                      <button
                        type="button"
                        className={`chunk-text-tab ${tab === 'embed' ? 'chunk-text-tab-active' : ''}`}
                        onClick={() => setTab(chunk.id, 'embed')}
                      >
                        embed_text
                      </button>
                    </div>

                    <pre className="chunk-pre">
                      {tab === 'raw' ? chunk.raw_text : chunk.embed_text}
                    </pre>

                    <div className="chunk-footer">
                      {chunk.block_ids.length > 0 && (
                        <span className="text-dim" style={{ fontSize: 10 }}>
                          blocks: {chunk.block_ids.slice(0, 4).join(', ')}{chunk.block_ids.length > 4 ? '…' : ''}
                        </span>
                      )}
                      {chunk.parent_id && (
                        <span className="text-dim" style={{ fontSize: 10 }}>
                          parent: {chunk.parent_id.slice(0, 8)}…
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </StageBlock>
  )
}
