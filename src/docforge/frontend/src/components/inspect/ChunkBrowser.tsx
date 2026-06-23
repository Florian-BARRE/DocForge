// ====== Code Summary ======
// <ChunkBrowser> — searchable, filterable, sortable view over a document's
// chunks.  Orchestrates data loading, the per-page block cache shared by every
// open chunk inspector, and lazy figure-crop fetching.  Filtering/sorting lives
// in useChunkFilter; the stats bar and the chunk cards are extracted components.

// ====== Standard Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { BlockInfo, ChunkResponse, Document } from '../../api/types'
import { getBlockFigure, getPage, listChunks } from '../../api/client'

// ====== Local Project Imports ======
import { chunkPages } from './chunkHelpers'
import { ChunkCard } from './ChunkRow'
import { ChunkStats } from './ChunkStats'
import { useChunkFilter } from './useChunkFilter'

interface Props {
  doc: Document
  collectionId: string
}

/**
 * Searchable, filterable, sortable inspector over a document's chunks.
 *
 * Args:
 *   doc:          The document whose chunks are inspected.
 *   collectionId: UUID of the owning collection.
 */
export function ChunkBrowser({ doc, collectionId }: Props) {
  const [chunks, setChunks] = useState<ChunkResponse[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [openId, setOpenId] = useState<string | null>(null)

  // Per-page block cache shared across every open chunk inspector — chunks that
  // overlap a page only pay for it once.
  const [pageBlocks, setPageBlocks] = useState<Record<number, BlockInfo[]>>({})
  const [loadingPages, setLoadingPages] = useState<Set<number>>(new Set())
  const [figureSrcs, setFigureSrcs] = useState<Record<string, string>>({})

  // ── Search / filter / sort state + derived view ───────────────────────────
  const {
    search, setSearch,
    strategyFilter, setStrategyFilter,
    minTokens, setMinTokens,
    maxTokens, setMaxTokens,
    sortKey, setSortKey,
    availableStrategies,
    view,
  } = useChunkFilter(chunks)

  // ── Load chunks ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (doc.status !== 'done') return
    let cancelled = false
    setLoading(true)
    setError(null)
    listChunks(collectionId, doc.id, { limit: 500 })
      .then(res => {
        if (cancelled) return
        setChunks(res.chunks)
        setTotal(res.total)
      })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [doc.id, doc.status, collectionId])

  // ── On expansion, lazy-load pages referenced by the chunk ─────────────────
  async function ensurePages(chunk: ChunkResponse) {
    const wanted = chunkPages(chunk).filter(p => !(p in pageBlocks) && !loadingPages.has(p))
    if (wanted.length === 0) return
    setLoadingPages(prev => {
      const s = new Set(prev); wanted.forEach(p => s.add(p)); return s
    })
    await Promise.allSettled(wanted.map(async (p) => {
      try {
        const res = await getPage(collectionId, doc.id, p)
        setPageBlocks(prev => ({ ...prev, [p]: res.blocks }))
      } catch { /* swallow */ }
    }))
    setLoadingPages(prev => {
      const s = new Set(prev); wanted.forEach(p => s.delete(p)); return s
    })
  }

  function toggleOpen(chunk: ChunkResponse) {
    const willOpen = openId !== chunk.id
    setOpenId(willOpen ? chunk.id : null)
    if (willOpen) {
      void ensurePages(chunk)
      // Figure chunks: pre-fetch the figure crop URL.
      if (chunk.strategy === 'figure' && chunk.block_ids[0] && figureSrcs[chunk.id] === undefined) {
        getBlockFigure(collectionId, doc.id, chunk.block_ids[0])
          .then(r => setFigureSrcs(prev => ({ ...prev, [chunk.id]: r.url })))
          .catch(() => setFigureSrcs(prev => ({ ...prev, [chunk.id]: '' })))
      }
    }
  }

  if (doc.status !== 'done') {
    return (
      <div className="text-muted" style={{ fontSize: 12, padding: 12 }}>
        {doc.status === 'running' || doc.status === 'pending'
          ? 'Chunking in progress…'
          : 'No chunks available.'}
      </div>
    )
  }
  if (loading) return <div className="text-muted" style={{ padding: 12 }}><span className="spin">⟳</span> Loading chunks…</div>
  if (error) return <div className="error-banner">{error}</div>

  return (
    <div className="chunk-browser">
      {/* ── Stats header ── */}
      <ChunkStats chunks={chunks} />

      {/* ── Toolbar ── */}
      <div className="chunk-browser-toolbar">
        <input
          className="input"
          type="text"
          placeholder="Search raw / embed text or chunk id…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: 200, fontSize: 12 }}
        />
        <select
          className="input select"
          value={strategyFilter}
          onChange={e => setStrategyFilter(e.target.value)}
          style={{ width: 130, fontSize: 12 }}
        >
          <option value="all">All strategies</option>
          {availableStrategies.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          className="input"
          type="number"
          placeholder="min tok"
          value={minTokens}
          onChange={e => setMinTokens(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          style={{ width: 80, fontSize: 12 }}
        />
        <input
          className="input"
          type="number"
          placeholder="max tok"
          value={maxTokens}
          onChange={e => setMaxTokens(e.target.value === '' ? '' : parseInt(e.target.value, 10))}
          style={{ width: 80, fontSize: 12 }}
        />
        <select
          className="input select"
          value={sortKey}
          onChange={e => setSortKey(e.target.value as typeof sortKey)}
          style={{ width: 150, fontSize: 12 }}
        >
          <option value="order">Reading order</option>
          <option value="tokens-desc">Tokens ↓</option>
          <option value="tokens-asc">Tokens ↑</option>
          <option value="pages">First page</option>
        </select>
        <span className="text-dim" style={{ fontSize: 11 }}>
          {view.length}/{total}
        </span>
      </div>

      {/* ── List ── */}
      <div className="chunk-browser-list">
        {view.length === 0 && (
          <div className="text-dim" style={{ fontSize: 11, padding: 12 }}>
            No chunks match the current filter.
          </div>
        )}
        {view.map((chunk, idx) => {
          const isOpen = openId === chunk.id
          return (
            <ChunkCard
              key={chunk.id}
              rank={idx + 1}
              chunk={chunk}
              isOpen={isOpen}
              onToggle={() => toggleOpen(chunk)}
              pageBlocks={pageBlocks}
              loadingPages={loadingPages}
              figureSrc={figureSrcs[chunk.id]}
            />
          )
        })}
      </div>
    </div>
  )
}
