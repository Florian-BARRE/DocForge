// ====== Code Summary ======
// Stage S4/S5 block — shows chunks with their raw_text, embed_text, and provenance.
// Each chunk is collapsed by default; click to expand raw_text / embed_text tabs.

import { useState, useEffect } from 'react'
import type { BlockInfo, ChunkResponse, Document } from '../../../api/types'
import { getBlockFigure, getPage, listChunks } from '../../../api/client'
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

  // Per-page block cache so chunks that share a page reuse a single fetch.
  //   pageNum (0-idx) → list of BlockInfo on that page
  const [pageBlocks, setPageBlocks] = useState<Record<number, BlockInfo[]>>({})
  const [loadingPages, setLoadingPages] = useState<Set<number>>(new Set())

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

  /**
   * Lazy-load every page the chunk references so we can resolve its block_ids
   * to full BlockInfo objects.  Results are cached per page; chunks sharing a
   * page reuse the same fetch.
   */
  async function fetchChunkPages(chunk: ChunkResponse) {
    const pages = getPages(chunk)
    const needed = pages.filter(p => !(p in pageBlocks) && !loadingPages.has(p))
    if (needed.length === 0) return
    setLoadingPages(prev => {
      const s = new Set(prev)
      needed.forEach(p => s.add(p))
      return s
    })
    await Promise.allSettled(needed.map(async (p) => {
      try {
        const res = await getPage(collectionId, doc.id, p)
        setPageBlocks(prev => ({ ...prev, [p]: res.blocks }))
      } catch { /* leave the page unloaded; the chunk will display a fallback */ }
    }))
    setLoadingPages(prev => {
      const s = new Set(prev)
      needed.forEach(p => s.delete(p))
      return s
    })
  }

  function toggleChunk(id: string, chunk: ChunkResponse) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        void fetchFigureSrc(chunk)
        void fetchChunkPages(chunk)
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

                    {/* IR blocks this chunk was assembled from — full block detail
                        with type badge, page, text and (for FIGURE/TABLE) the type_data. */}
                    <IRBlocksList
                      chunk={chunk}
                      pageBlocks={pageBlocks}
                      loadingPages={loadingPages}
                    />

                    <div className="chunk-footer">
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

// ── IRBlocksList — renders the IR blocks a chunk references ──────────────────

function IRBlocksList({
  chunk, pageBlocks, loadingPages,
}: {
  chunk: ChunkResponse
  pageBlocks: Record<number, BlockInfo[]>
  loadingPages: Set<number>
}) {
  const pages = getChunkPages(chunk)
  const wantedIds = new Set(chunk.block_ids)
  // Gather BlockInfo across every page in the chunk, preserve chunk.block_ids order.
  const allLoaded = pages.every(p => p in pageBlocks)
  const anyLoading = pages.some(p => loadingPages.has(p))
  const byId: Record<string, BlockInfo> = {}
  pages.forEach(p => {
    (pageBlocks[p] ?? []).forEach(b => {
      if (wantedIds.has(b.id)) byId[b.id] = b
    })
  })
  const ordered = chunk.block_ids.map(id => byId[id]).filter(Boolean) as BlockInfo[]

  return (
    <div className="picker" style={{ marginTop: 8 }}>
      <div className="picker-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>IR blocks</span>
        <span className="text-dim mono" style={{ fontSize: 10 }}>
          {chunk.block_ids.length}
        </span>
        {anyLoading && !allLoaded && (
          <span className="text-dim" style={{ fontSize: 10 }}>
            <span className="spin">⟳</span> loading…
          </span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {ordered.length === 0 && !anyLoading && (
          <span className="text-dim" style={{ fontSize: 10 }}>
            blocks not loaded — try collapsing and re-opening the chunk.
          </span>
        )}
        {ordered.map(b => <IRBlockRow key={b.id} block={b} />)}
      </div>
    </div>
  )
}

function IRBlockRow({ block }: { block: BlockInfo }) {
  const [open, setOpen] = useState(false)
  const color = blockTypeColor(block.type)
  const isFigure = block.type.toLowerCase() === 'figure'
  const isTable = block.type.toLowerCase() === 'table'
  const td = block.type_data as Record<string, unknown> | null | undefined
  const preview = (block.text ?? '').slice(0, 90)

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 4,
      padding: 4, background: 'var(--panel-bg, transparent)',
    }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          cursor: 'pointer', fontSize: 11, flexWrap: 'wrap',
        }}
      >
        <span className="tag" style={{
          color, borderColor: color + '40', background: color + '15',
          fontSize: 9, padding: '1px 5px',
        }}>{block.type}</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>
          p.{block.page + 1}
        </span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>
          {block.id.slice(0, 16)}…
        </span>
        {isFigure && td?.kind != null && (
          <span className="tag" style={{ fontSize: 9, padding: '1px 5px' }}>
            {String(td.kind)}
          </span>
        )}
        <span className="text-dim" style={{ fontSize: 11, flex: 1, minWidth: 0,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {preview || (isFigure ? '(figure)' : isTable ? '(table)' : '')}
        </span>
        <span className="text-dim" style={{ fontSize: 10 }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div className="fadein" style={{ marginTop: 6, paddingTop: 6, borderTop: '1px dashed var(--border)' }}>
          {block.bbox.length === 4 && (
            <div style={{ fontSize: 10 }}>
              <span className="text-dim">bbox: </span>
              <span className="mono">[{block.bbox.map(v => v.toFixed(3)).join(', ')}]</span>
            </div>
          )}
          {block.text && (
            <pre className="chunk-pre" style={{
              fontSize: 10, marginTop: 4, maxHeight: 160, overflow: 'auto',
            }}>{block.text}</pre>
          )}
          {/* Figure / table type_data summary */}
          {isFigure && td && (
            <div style={{ fontSize: 10, marginTop: 4 }}>
              {td.relevance != null && <div><span className="text-dim">relevance:</span> <span className="mono">{Number(td.relevance).toFixed(3)}</span></div>}
              {td.ocr_text != null && <div className="text-dim" style={{ marginTop: 2 }}>ocr_text: <span className="mono">{String(td.ocr_text).slice(0, 200)}{String(td.ocr_text).length > 200 ? '…' : ''}</span></div>}
              {td.description != null && <div className="text-dim" style={{ marginTop: 2 }}>description: <span className="mono">{String(td.description).slice(0, 200)}{String(td.description).length > 200 ? '…' : ''}</span></div>}
              {td.data_table != null && Array.isArray(td.data_table) && (
                <div className="text-dim" style={{ marginTop: 2 }}>
                  data_table: {(td.data_table as string[][]).length} rows ×{' '}
                  {((td.data_table as string[][])[0]?.length ?? 0)} cols
                </div>
              )}
            </div>
          )}
          {isTable && td && (
            <div style={{ fontSize: 10, marginTop: 4 }}>
              <span className="text-dim">{(td.n_rows as number) ?? '?'}×{(td.n_cols as number) ?? '?'} table</span>
            </div>
          )}
          {/* Block chain traces — classifier / OCR / VLM lineage for this block */}
          {block.chain_traces && block.chain_traces.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <span className="text-dim" style={{ fontSize: 10 }}>chain traces:</span>
              {block.chain_traces.map((t, i) => {
                const n = t.attempts?.length ?? 0
                return (
                  <div key={i} className="mono text-dim" style={{ fontSize: 10, marginLeft: 8 }}>
                    {t.stage} → {t.final_provider ?? '(exhausted)'} ({n} attempt{n !== 1 ? 's' : ''})
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function blockTypeColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'heading':       return '#a78bfa'
    case 'paragraph':     return '#94a3b8'
    case 'figure':        return '#6366f1'
    case 'table':         return '#34d399'
    case 'list_item':     return '#60a5fa'
    case 'caption':       return '#f59e0b'
    case 'code':          return '#f97316'
    case 'formula':       return '#ec4899'
    case 'header_footer': return '#64748b'
    default:              return '#94a3b8'
  }
}

function getChunkPages(chunk: ChunkResponse): number[] {
  const prov = chunk.prov as Record<string, unknown>
  const pages = prov?.pages
  if (Array.isArray(pages)) return pages as number[]
  return []
}
