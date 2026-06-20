// ====== Code Summary ======
// Search playground — interactive hybrid search with visible weight sliders,
// auto-search when parameters change, and query-term highlighting in results.
// Replaces the buried discovery form controls with first-class slider UI.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Collection, Document, SearchResultItem } from '../../api/types'
import { listCollections, listDocuments, searchDocuments } from '../../api/client'

/**
 * Interactive hybrid search playground.
 *
 * Owns dense/sparse weight sliders and top_k presets directly rather than
 * delegating to the discovery form, so parameter changes are immediate and
 * visible. Re-runs the current query automatically when any slider moves.
 */
export function SearchView() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [collectionId, setCollectionId] = useState<string>('')
  const [docMap, setDocMap] = useState<Record<string, Document>>({})

  const [query, setQuery] = useState('')
  const [denseWeight, setDenseWeight] = useState(0.5)
  const [sparseWeight, setSparseWeight] = useState(0.5)
  const [topK, setTopK] = useState(10)

  const [results, setResults] = useState<SearchResultItem[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | undefined>()
  const [searched, setSearched] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // Holds the last query that was actually sent — auto-search watches this.
  const lastQueryRef = useRef<string>('')

  // 1. Load collections on mount.
  useEffect(() => {
    listCollections()
      .then(res => {
        setCollections(res.collections)
        if (res.collections.length > 0) setCollectionId(res.collections[0].id)
      })
      .catch(() => {})
  }, [])

  // 2. Pre-fetch documents to resolve filenames in result cards.
  useEffect(() => {
    if (!collectionId) return
    listDocuments(collectionId, { limit: 200 })
      .then(res => {
        const map: Record<string, Document> = {}
        res.documents.forEach(d => { map[d.id] = d })
        setDocMap(map)
      })
      .catch(() => {})
  }, [collectionId])

  // 3. Core search function — memoised so the auto-search effect can depend on it.
  const runSearch = useCallback(async (
    q: string, dense: number, sparse: number, k: number,
  ) => {
    if (!collectionId || !q.trim()) return
    setSearching(true)
    setError(null)
    setNote(undefined)
    try {
      const res = await searchDocuments(collectionId, q.trim(), {
        top_k: k,
        weights: { dense, sparse },
      })
      setResults(res.results)
      setNote(res.note ?? undefined)
      setSearched(true)
    } catch (err) {
      setError(String(err))
    } finally {
      setSearching(false)
    }
  }, [collectionId])

  // 4. Manual search (query input + Search button).
  function handleSearch(e?: React.FormEvent) {
    e?.preventDefault()
    const q = query.trim()
    if (!q) return
    lastQueryRef.current = q
    void runSearch(q, denseWeight, sparseWeight, topK)
  }

  // 5. Auto-search when weights or top_k change — only if a query was already run.
  useEffect(() => {
    const q = lastQueryRef.current
    if (!q || !collectionId) return
    const timer = setTimeout(() => {
      void runSearch(q, denseWeight, sparseWeight, topK)
    }, 500)
    return () => clearTimeout(timer)
  }, [denseWeight, sparseWeight, topK, collectionId, runSearch])

  function toggleResult(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const maxScore = results.length > 0 ? Math.max(...results.map(r => r.score)) : 1

  return (
    <div className="search-view fadein">
      <div className="panel-header">
        <div className="panel-title">
          Search Playground
          {searching && (
            <span className="spin" style={{ fontSize: 13, marginLeft: 8, color: 'var(--accent)' }}>⟳</span>
          )}
        </div>
      </div>

      {/* ── Collection picker ── */}
      <div className="field-row" style={{ marginBottom: 14 }}>
        <span className="field-label">Collection</span>
        <select
          className="input select"
          value={collectionId}
          onChange={e => {
            setCollectionId(e.target.value)
            setSearched(false)
            setResults([])
            lastQueryRef.current = ''
          }}
          style={{ maxWidth: 280 }}
        >
          {collections.length === 0 && <option value="">No collections</option>}
          {collections.map(col => (
            <option key={col.id} value={col.id}>{col.name}</option>
          ))}
        </select>
      </div>

      {/* ── Query input ── */}
      <form onSubmit={handleSearch}>
        <div className="search-query-row">
          <input
            className="input search-query-input"
            type="text"
            placeholder="Enter your search query…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={searching || !collectionId || !query.trim()}
          >
            Search
          </button>
        </div>
      </form>

      {/* ── Parameters panel ── */}
      <div className="search-params-panel">
        <div className="search-params-title">Hybrid Search Parameters</div>
        <div className="search-params-grid">
          <WeightSlider
            label="Dense"
            hint="vector · semantic similarity"
            value={denseWeight}
            color="var(--accent)"
            onChange={setDenseWeight}
          />
          <WeightSlider
            label="Sparse"
            hint="BM25 · keyword matching"
            value={sparseWeight}
            color="#f59e0b"
            onChange={setSparseWeight}
          />
          <div className="topk-control">
            <span className="weight-label">Top K</span>
            <div className="topk-presets">
              {[5, 10, 20, 50].map(k => (
                <button
                  key={k}
                  type="button"
                  className={`btn btn-ghost topk-btn${topK === k ? ' topk-btn-active' : ''}`}
                  onClick={() => setTopK(k)}
                >{k}</button>
              ))}
            </div>
          </div>
        </div>
        {lastQueryRef.current && (
          <div className="text-dim" style={{ fontSize: 10, marginTop: 8 }}>
            Slider changes automatically re-run <em>"{lastQueryRef.current}"</em>.
          </div>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}
      {note && (
        <div className="info-banner">
          <span className="info-icon">ℹ</span>{note}
        </div>
      )}

      {/* ── Empty state ── */}
      {searched && results.length === 0 && !error && (
        <div className="empty" style={{ padding: '32px 0' }}>
          <div className="empty-icon">🔍</div>
          <div>No results found.</div>
        </div>
      )}

      {/* ── Results ── */}
      {results.length > 0 && (
        <div className="search-results">
          <div className="search-results-hdr">
            <span className="section-title" style={{ fontSize: 12 }}>
              {results.length} result{results.length !== 1 ? 's' : ''}
            </span>
            <span className="text-dim" style={{ fontSize: 10 }}>
              dense {denseWeight.toFixed(2)} · sparse {sparseWeight.toFixed(2)} · k={topK}
            </span>
          </div>
          {results.map((item, idx) => (
            <ResultCard
              key={item.chunk_id}
              item={item}
              idx={idx}
              maxScore={maxScore}
              query={lastQueryRef.current}
              docFilename={
                docMap[item.document_id]?.filename
                ?? item.document_id.slice(0, 12) + '…'
              }
              isOpen={expanded.has(item.chunk_id)}
              onToggle={() => toggleResult(item.chunk_id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ── WeightSlider ─────────────────────────────────────────────────────────────

/**
 * A labelled range slider for a search weight (0 → 1, step 0.05).
 * Shows the current value in the header row as a coloured number.
 */
function WeightSlider({
  label, hint, value, color, onChange,
}: {
  label: string
  hint: string
  value: number
  color: string
  onChange: (v: number) => void
}) {
  const fillPct = `${value * 100}%`
  return (
    <div className="weight-control">
      <div className="weight-control-header">
        <span className="weight-label">{label}</span>
        <span className="weight-hint">{hint}</span>
        <span className="weight-value mono" style={{ color }}>{value.toFixed(2)}</span>
      </div>
      {/* Visual track: a background fill behind the native range input */}
      <div className="weight-slider-wrap">
        <div className="weight-slider-fill" style={{ width: fillPct, background: color + '30' }} />
        <input
          type="range"
          className="weight-slider"
          min={0} max={1} step={0.05}
          value={value}
          style={{ '--thumb-color': color } as React.CSSProperties}
          onChange={e => onChange(parseFloat(e.target.value))}
        />
      </div>
    </div>
  )
}

// ── ResultCard ───────────────────────────────────────────────────────────────

/**
 * A single search result card. Collapsed state shows a highlighted 200-char
 * preview; expanded state shows the full raw_text + provenance footer.
 */
function ResultCard({
  item, idx, maxScore, query, docFilename, isOpen, onToggle,
}: {
  item: SearchResultItem
  idx: number
  maxScore: number
  query: string
  docFilename: string
  isOpen: boolean
  onToggle: () => void
}) {
  const relPct = maxScore > 0 ? Math.round((item.score / maxScore) * 100) : 0
  const { label, color } = scoreLabel(relPct)

  return (
    <div className="result-card">
      {/* ── Header row ── */}
      <div className="result-header" onClick={onToggle}>
        <span className="result-rank text-dim">#{idx + 1}</span>

        {/* Score block: bar + % + qualitative label */}
        <div className="result-score-block">
          <div className="result-score-bar">
            <div className="result-score-fill" style={{ width: `${relPct}%`, background: color }} />
          </div>
          <span className="mono" style={{ fontSize: 11, color, minWidth: 32 }}>{relPct}%</span>
          <span className="result-quality-label" style={{ color }}>{label}</span>
        </div>

        {/* Doc / page / strategy meta */}
        <div className="result-meta-block">
          <span className="result-filename text-muted">{docFilename}</span>
          {item.pages.length > 0 && (
            <span className="mono text-dim" style={{ fontSize: 10 }}>
              p.{item.pages.join(',')}
            </span>
          )}
          <span className="tag" style={{ fontSize: 9, padding: '1px 5px' }}>{item.strategy}</span>
          <span className="mono text-dim" style={{ fontSize: 10 }}>{item.token_count} tok</span>
        </div>

        <span className="result-expand text-dim">{isOpen ? '▲' : '▼'}</span>
      </div>

      {/* ── Body: preview / full text ── */}
      <div className={`result-body${isOpen ? ' result-body-open' : ' result-body-closed'}`}>
        <div className="result-raw-text">
          <HighlightedText
            text={isOpen ? item.raw_text : item.raw_text.slice(0, 200)}
            query={query}
          />
          {!isOpen && item.raw_text.length > 200 && (
            <span className="text-dim"> …</span>
          )}
        </div>
        {isOpen && (
          <div className="result-footer">
            <span className="mono text-dim" style={{ fontSize: 10 }}>
              score {item.score.toFixed(4)} · {item.strategy} · {item.token_count} tok
              · {item.chunk_id.slice(0, 8)}…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

// ── HighlightedText ──────────────────────────────────────────────────────────

/**
 * Splits text on query terms (>2 chars) and wraps matches in <mark> elements.
 * Uses odd-index detection on capture-group split — safe because there is
 * exactly one capture group in the regex.
 */
function HighlightedText({ text, query }: { text: string; query: string }) {
  const terms = useMemo(
    () => query.trim().split(/\s+/).filter(t => t.length > 2),
    [query],
  )
  if (terms.length === 0) return <>{text}</>

  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)

  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1
          ? <mark key={i} className="search-highlight">{part}</mark>
          : part,
      )}
    </>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function scoreLabel(pct: number): { label: string; color: string } {
  if (pct >= 85) return { label: 'Strong', color: 'var(--s-done)' }
  if (pct >= 65) return { label: 'Good',   color: 'var(--accent)' }
  if (pct >= 40) return { label: 'Moderate', color: 'var(--s-running)' }
  return           { label: 'Weak',     color: 'var(--text-dim)' }
}
