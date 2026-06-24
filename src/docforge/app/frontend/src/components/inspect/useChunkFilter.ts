// ====== Code Summary ======
// useChunkFilter — encapsulates the ChunkBrowser search/filter/sort state and
// derives the filtered + sorted chunk list plus the available-strategy set.
// Keeps the rendering component free of filtering logic.

// ====== Standard Library Imports ======
import { useMemo, useState } from 'react'

// ====== Internal Project Imports ======
import type { ChunkResponse } from '../../api/types'

// ====== Local Project Imports ======
import { firstPage } from './chunkHelpers'

export type SortKey = 'order' | 'tokens-desc' | 'tokens-asc' | 'pages'

/** State + derived data returned by {@link useChunkFilter}. */
export interface ChunkFilterState {
  search: string
  setSearch: (v: string) => void
  strategyFilter: string
  setStrategyFilter: (v: string) => void
  minTokens: number | ''
  setMinTokens: (v: number | '') => void
  maxTokens: number | ''
  setMaxTokens: (v: number | '') => void
  sortKey: SortKey
  setSortKey: (v: SortKey) => void
  availableStrategies: string[]
  view: ChunkResponse[]
}

/**
 * Manage chunk search/filter/sort state and derive the resulting view.
 *
 * Args:
 *   chunks: The full set of chunks fetched for the document.
 *
 * Returns:
 *   The filter state setters plus the derived available strategies and the
 *   filtered + sorted chunk list.
 */
export function useChunkFilter(chunks: ChunkResponse[]): ChunkFilterState {
  const [search, setSearch] = useState('')
  const [strategyFilter, setStrategyFilter] = useState<string>('all')
  const [minTokens, setMinTokens] = useState<number | ''>('')
  const [maxTokens, setMaxTokens] = useState<number | ''>('')
  const [sortKey, setSortKey] = useState<SortKey>('order')

  // ── Available strategies (for the filter dropdown) ────────────────────────
  const availableStrategies = useMemo(() => {
    const s = new Set<string>()
    chunks.forEach(c => s.add(c.strategy))
    return Array.from(s).sort()
  }, [chunks])

  // ── Apply search / filters / sort ─────────────────────────────────────────
  const view = useMemo(() => {
    const q = search.trim().toLowerCase()
    const lo = typeof minTokens === 'number' ? minTokens : -Infinity
    const hi = typeof maxTokens === 'number' ? maxTokens : Infinity

    const filtered = chunks.filter(c => {
      if (strategyFilter !== 'all' && c.strategy !== strategyFilter) return false
      if (c.token_count < lo || c.token_count > hi) return false
      if (q && !(
        c.raw_text.toLowerCase().includes(q) ||
        c.embed_text.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q)
      )) return false
      return true
    })

    switch (sortKey) {
      case 'tokens-desc': filtered.sort((a, b) => b.token_count - a.token_count); break
      case 'tokens-asc':  filtered.sort((a, b) => a.token_count - b.token_count); break
      case 'pages':       filtered.sort((a, b) => firstPage(a) - firstPage(b)); break
      case 'order':       /* keep server order */ break
    }
    return filtered
  }, [chunks, search, strategyFilter, minTokens, maxTokens, sortKey])

  return {
    search, setSearch,
    strategyFilter, setStrategyFilter,
    minTokens, setMinTokens,
    maxTokens, setMaxTokens,
    sortKey, setSortKey,
    availableStrategies,
    view,
  }
}
