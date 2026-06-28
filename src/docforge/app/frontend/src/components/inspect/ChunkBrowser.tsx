// ====== Code Summary ======
// <ChunkBrowser> — searchable, filterable, sortable view over a document's
// chunks.  Orchestrates data loading with server-side pagination (limit/offset),
// the per-page block cache shared by every open chunk inspector, and lazy
// figure-crop fetching.  Filtering/sorting lives in useChunkFilter; the stats
// bar and chunk cards are extracted components.

// ====== Standard Library Imports ======
import { useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import type { BlockInfo, ChunkResponse, Document } from '../../api/types'
import { getBlockFigure, getPage, listChunks } from '../../api/client'
import { EmptyState } from '../ui/primitives/EmptyState'
import { Spinner } from '../ui/primitives/Spinner'

// ====== Local Project Imports ======
import { chunkPages } from './chunkHelpers'
import { ChunkCard } from './ChunkRow'
import { ChunkStats } from './ChunkStats'
import { useChunkFilter } from './useChunkFilter'

// ── Constants ─────────────────────────────────────────────────────────────────

/** Number of chunks loaded per page. */
const PAGE_SIZE = 100

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  doc: Document
  collectionId: string
  /**
   * When set, auto-opens this chunk id without affecting the search input.
   * Set by DocDetailView when the user jumps from in-document search.
   */
  jumpChunkId?: string | null
  /**
   * When false, chunk edit controls are hidden.
   * Defaults to true.
   */
  canWrite?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Searchable, filterable, sortable inspector over a document's chunks.
 *
 * Pagination: loads PAGE_SIZE chunks at a time from the server.  A "Load more"
 * button appends the next page.  The counter shows how many chunks are currently
 * loaded vs the server total, and how many match the active client-side filters.
 *
 * Jump-to-chunk: when jumpChunkId is set, the target chunk is opened without
 * polluting the search input.  If the chunk is not yet in the loaded set, the
 * browser loads additional pages until it is found.
 *
 * Args:
 *   doc:          The document whose chunks are inspected.
 *   collectionId: UUID of the owning collection.
 *   jumpChunkId:  When non-null, opens this chunk on arrival without affecting
 *                 the visible text search box.
 *   canWrite:     When false, hides write-only controls (Edit tab).
 */
export function ChunkBrowser({ doc, collectionId, jumpChunkId, canWrite = true }: Props) {
  const [chunks, setChunks]   = useState<ChunkResponse[]>([])
  const [total, setTotal]     = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const [openId, setOpenId] = useState<string | null>(null)
  // Track the last jumpChunkId we handled to avoid re-jumping on re-renders.
  const lastJumpRef = useRef<string | null>(null)
  // Pending jump: set when the jump target isn't yet in the loaded set,
  // cleared once it is found (triggers more pages to load automatically).
  const pendingJumpRef = useRef<string | null>(null)

  // Per-page block cache shared across every open chunk inspector.
  const [pageBlocks, setPageBlocks]     = useState<Record<number, BlockInfo[]>>({})
  const [loadingPages, setLoadingPages] = useState<Set<number>>(new Set())
  const [figureSrcs, setFigureSrcs]     = useState<Record<string, string>>({})

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

  // ── Initial chunk load ────────────────────────────────────────────────────
  useEffect(() => {
    if (doc.status !== 'done') return
    let cancelled = false
    setLoading(true)
    setError(null)
    setChunks([])
    setTotal(0)
    listChunks(collectionId, doc.id, { limit: PAGE_SIZE, offset: 0 })
      .then(res => {
        if (cancelled) return
        setChunks(res.chunks)
        setTotal(res.total)
      })
      .catch(err => { if (!cancelled) setError(String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [doc.id, doc.status, collectionId])

  // ── Auto-load more pages when a pending jump target is not yet loaded ─────
  useEffect(() => {
    if (!pendingJumpRef.current || loading || loadingMore) return

    const found = chunks.some(c => c.id === pendingJumpRef.current)
    if (found) {
      // The jump target is now in the loaded set — open it.
      setOpenId(pendingJumpRef.current)
      pendingJumpRef.current = null
    } else if (chunks.length < total) {
      // Load the next page to search for the jump target.
      void loadMore()
    } else {
      // All chunks loaded and target not found — clear the pending jump.
      pendingJumpRef.current = null
    }
  // Intentionally excluding loadMore from deps to avoid circular dependency.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chunks, total, loading, loadingMore])

  // ── Load more (next page) ─────────────────────────────────────────────────

  /**
   * Appends the next page of chunks to the loaded set.
   *
   * Uses the current loaded count as the offset so pages do not overlap.
   * This is safe for sequential display where chunks are not reordered between
   * pages by the server.
   */
  async function loadMore() {
    if (loadingMore || loading || chunks.length >= total) return
    setLoadingMore(true)
    try {
      const res = await listChunks(collectionId, doc.id, {
        limit:  PAGE_SIZE,
        offset: chunks.length,
      })
      setChunks(prev => [...prev, ...res.chunks])
      setTotal(res.total)
    } catch { /* swallow — user can retry */ }
    setLoadingMore(false)
  }

  // ── Jump to a specific chunk (from in-document search) ────────────────────
  // Opens the target chunk WITHOUT putting its UUID in the visible search input.
  // If the chunk is not in the currently loaded set, sets pendingJumpRef which
  // triggers the auto-load effect above to fetch more pages until it is found.
  useEffect(() => {
    if (!jumpChunkId || jumpChunkId === lastJumpRef.current) return
    lastJumpRef.current = jumpChunkId

    const inLoadedSet = chunks.some(c => c.id === jumpChunkId)
    if (inLoadedSet) {
      // Chunk is already loaded — open it immediately.
      setOpenId(jumpChunkId)
    } else {
      // Defer opening until the chunk appears in the loaded set.
      pendingJumpRef.current = jumpChunkId
    }
  }, [jumpChunkId, chunks])

  // ── Propagate chunk text edits to the browser list ────────────────────────
  function onChunkUpdated(chunkId: string, updates: { raw_text: string; embed_text: string }) {
    setChunks(prev => prev.map(c => c.id === chunkId ? { ...c, ...updates } : c))
  }

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

  // ── Guard: doc not done yet ───────────────────────────────────────────────

  if (doc.status !== 'done') {
    if (doc.status === 'running' || doc.status === 'pending') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 12 }}>
          <Spinner size={14} />
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Chunking in progress…</span>
        </div>
      )
    }
    return <EmptyState message="No chunks available." />
  }

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: 12 }}>
      <Spinner size={14} />
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading chunks…</span>
    </div>
  )

  if (error) return <div className="error-banner">{error}</div>

  // ── Counter text: honest about client filtering vs server total ───────────
  // "12 shown · 100 of 340 loaded" or "12 / 100" when all loaded.
  const counterText = chunks.length < total
    ? `${view.length} shown · ${chunks.length} of ${total} loaded`
    : `${view.length} / ${total}`

  return (
    <div className="chunk-browser">
      {/* ── Stats header ── */}
      <ChunkStats chunks={chunks} />

      {/* ── Toolbar ── */}
      <div className="chunk-browser-toolbar">
        <input
          className="input"
          type="text"
          placeholder="Search raw / embed text…"
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
        {/* Honest counter: filtered view / loaded (of server total) */}
        <span className="text-dim chunk-browser-counter">
          {counterText}
        </span>
      </div>

      {/* ── List ── */}
      <div className="chunk-browser-list">
        {view.length === 0 && (
          <EmptyState message="No chunks match the current filters." />
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
              collectionId={collectionId}
              canWrite={canWrite}
              onChunkUpdated={onChunkUpdated}
            />
          )
        })}
      </div>

      {/* ── Load more button (shown when server has more chunks) ── */}
      {chunks.length < total && (
        <div className="chunk-load-more-bar">
          <button
            type="button"
            className="btn"
            onClick={() => void loadMore()}
            disabled={loadingMore}
          >
            {loadingMore ? (
              <>
                <Spinner size={11} />
                Loading…
              </>
            ) : (
              `Load more (${total - chunks.length} remaining)`
            )}
          </button>
        </div>
      )}
    </div>
  )
}
