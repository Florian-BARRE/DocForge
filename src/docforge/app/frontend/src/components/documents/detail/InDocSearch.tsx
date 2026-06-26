// ====== Code Summary ======
// InDocSearch — in-document semantic search bar for the document detail view.
// Calls searchWithinDocument and renders ranked chunk results.  Clicking
// "Go to chunk" triggers the parent to jump to that chunk in the Chunks tab.

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { HttpError, searchWithinDocument } from '../../../api/client'
import type { SearchResultItem } from '../../../api/types'

interface InDocSearchProps {
  /** Collection this document belongs to. */
  collectionId: string
  /** Document to search within. */
  docId: string
  /** Called when the user wants to jump to a specific chunk. */
  onJumpToChunk: (chunkId: string) => void
}

/**
 * In-document semantic search bar.
 *
 * Submits a query to searchWithinDocument and renders the ranked results.
 * Each result shows a score bar, page info, and a "Go to chunk" button that
 * triggers the parent to navigate to the Chunks tab at that chunk.
 *
 * Args:
 *   collectionId:  UUID of the owning collection.
 *   docId:         UUID of the document to search within.
 *   onJumpToChunk: Callback fired with the chunk_id the user wants to inspect.
 */
export function InDocSearch({ collectionId, docId, onJumpToChunk }: InDocSearchProps) {
  const [query, setQuery]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const [hasRun, setHasRun]   = useState(false)

  // 1. Submit the search query.
  async function submit() {
    const q = query.trim()
    if (!q) return
    setLoading(true)
    setError(null)
    setHasRun(true)
    setOpenIdx(null)
    try {
      const res = await searchWithinDocument(collectionId, docId, q, { top_k: 10 })
      setResults(res.results)
    } catch (err) {
      const msg = err instanceof HttpError
        ? `Search error (HTTP ${err.status}): ${err.message}`
        : String(err)
      setError(msg)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  // 2. Submit on Enter key.
  function handleKey(e: React.KeyboardEvent) {
    if (e.key === 'Enter') void submit()
  }

  const maxScore = results.length > 0 ? Math.max(...results.map(r => r.score)) : 1

  return (
    <div className="indoc-search">
      {/* Search bar */}
      <div className="indoc-search-bar">
        <input
          type="text"
          className="input"
          placeholder="Find passages in this document…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKey}
          style={{ flex: 1, fontSize: 12 }}
        />
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void submit()}
          disabled={loading || !query.trim()}
          style={{ minWidth: 72, fontSize: 12 }}
        >
          {loading ? <span className="spin">⟳</span> : 'Search'}
        </button>
      </div>

      {/* Error */}
      {error && <div className="error-banner">{error}</div>}

      {/* Empty state */}
      {hasRun && !loading && results.length === 0 && !error && (
        <div className="text-dim" style={{ fontSize: 12, marginTop: 4 }}>No results found.</div>
      )}

      {/* Results list */}
      {results.length > 0 && (
        <div className="indoc-search-results">
          <div className="section-title">
            {results.length} result{results.length !== 1 ? 's' : ''}
          </div>
          {results.map((item, idx) => {
            const relPct = maxScore > 0 ? Math.round((item.score / maxScore) * 100) : 0
            const isOpen = openIdx === idx
            return (
              <InDocResultCard
                key={item.chunk_id}
                item={item}
                idx={idx}
                relPct={relPct}
                isOpen={isOpen}
                onToggle={() => setOpenIdx(isOpen ? null : idx)}
                onJump={() => onJumpToChunk(item.chunk_id)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── InDocResultCard — one ranked result ──────────────────────────────────────

interface InDocResultCardProps {
  item: SearchResultItem
  idx: number
  relPct: number
  isOpen: boolean
  onToggle: () => void
  onJump: () => void
}

/**
 * Compact result card for in-document search.
 *
 * Collapsed: score bar, pages, strategy, 160-char preview.
 * Expanded: full raw_text + chunk_id + "Go to chunk" button.
 *
 * Args:
 *   item:     Search result item from the API.
 *   idx:      0-based position in the list.
 *   relPct:   Relevance percentage relative to the best result (0–100).
 *   isOpen:   Whether the card is expanded.
 *   onToggle: Toggle expansion.
 *   onJump:   Navigate to this chunk in the Chunks tab.
 */
function InDocResultCard({ item, idx, relPct, isOpen, onToggle, onJump }: InDocResultCardProps) {
  const barColor = relPct >= 80
    ? 'var(--s-done)'
    : relPct >= 50
    ? 'var(--accent)'
    : 'var(--s-running)'

  return (
    <div className="indoc-result-card">
      {/* Header — always visible */}
      <div
        className="indoc-result-header"
        onClick={onToggle}
        role="button"
        tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onToggle() }}
      >
        <span className="mono text-dim" style={{ fontSize: 10, minWidth: 22 }}>#{idx + 1}</span>
        <div className="indoc-result-bar-wrap">
          <div className="indoc-result-bar" style={{ width: `${relPct}%`, background: barColor }} />
        </div>
        <span style={{ fontSize: 10, color: barColor, minWidth: 36, fontFamily: 'var(--font-mono)' }}>
          {relPct}%
        </span>
        <span className="tag" style={{ fontSize: 9 }}>{item.strategy}</span>
        {item.pages.length > 0 && (
          <span className="text-dim" style={{ fontSize: 10 }}>
            p.{item.pages.map(p => p + 1).join(',')}
          </span>
        )}
        <span className="text-dim" style={{ fontSize: 10 }}>{isOpen ? '▲' : '▼'}</span>
      </div>

      {/* Collapsed preview */}
      {!isOpen && (
        <div className="indoc-result-preview text-muted">
          {item.raw_text.slice(0, 160)}
          {item.raw_text.length > 160 && <span className="text-dim"> …</span>}
        </div>
      )}

      {/* Expanded — full text + jump button */}
      {isOpen && (
        <div className="indoc-result-body fadein">
          <pre className="indoc-result-full">{item.raw_text}</pre>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
            <span className="mono text-dim" style={{ fontSize: 10 }}>
              chunk {item.chunk_id.slice(0, 8)}…
            </span>
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className="btn"
              style={{ fontSize: 11, padding: '4px 10px' }}
              onClick={e => { e.stopPropagation(); onJump() }}
            >
              Go to chunk →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
