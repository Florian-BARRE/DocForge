// ====== Code Summary ======
// Search mode — collection picker + hybrid search bar + ranked result list.
// Shows score bars and chunk provenance (doc filename, pages).

import { useState, useEffect } from 'react'
import type { Collection, SearchResultItem, Document } from '../../api/types'
import { listCollections, listDocuments, searchDocuments } from '../../api/client'

/**
 * Hybrid search view. Users pick a collection, enter a query, select top-k,
 * and view ranked chunks with score bars and provenance metadata.
 */
export function SearchView() {
  const [collections, setCollections] = useState<Collection[]>([])
  const [collectionId, setCollectionId] = useState<string>('')
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(10)
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [docMap, setDocMap] = useState<Record<string, Document>>({})
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | undefined>()
  const [searched, setSearched] = useState(false)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // 1. Load collections on mount.
  useEffect(() => {
    listCollections()
      .then(res => {
        setCollections(res.collections)
        if (res.collections.length > 0) setCollectionId(res.collections[0].id)
      })
      .catch(() => { /* ignore */ })
  }, [])

  // 2. Pre-fetch document list for current collection to resolve filenames.
  useEffect(() => {
    if (!collectionId) return
    listDocuments(collectionId, { limit: 200 })
      .then(res => {
        const map: Record<string, Document> = {}
        res.documents.forEach(d => { map[d.id] = d })
        setDocMap(map)
      })
      .catch(() => { /* non-critical */ })
  }, [collectionId])

  // 3. Execute search.
  async function handleSearch(e?: React.FormEvent) {
    e?.preventDefault()
    if (!collectionId || !query.trim()) return
    setSearching(true)
    setError(null)
    setResults([])
    setNote(undefined)
    setSearched(false)
    try {
      const res = await searchDocuments(collectionId, query.trim(), { top_k: topK })
      setResults(res.results)
      setNote(res.note)
      setSearched(true)
    } catch (err) {
      setError(String(err))
    } finally {
      setSearching(false)
    }
  }

  function toggleResult(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) } else { next.add(id) }
      return next
    })
  }

  // Compute max score for normalizing the score bar.
  const maxScore = results.length > 0
    ? Math.max(...results.map(r => r.score))
    : 1

  return (
    <div className="search-view fadein">
      <div className="panel-header">
        <div className="panel-title">Search</div>
      </div>

      {/* Collection picker */}
      <div className="field-row" style={{ marginBottom: 14 }}>
        <span className="field-label">Collection</span>
        <select
          className="input select"
          value={collectionId}
          onChange={e => setCollectionId(e.target.value)}
          style={{ maxWidth: 300 }}
        >
          {collections.length === 0 && (
            <option value="">No collections</option>
          )}
          {collections.map(col => (
            <option key={col.id} value={col.id}>{col.name}</option>
          ))}
        </select>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSearch}>
        <div className="search-bar">
          <input
            className="input search-input"
            type="text"
            placeholder="Search documents…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={searching || !collectionId || !query.trim()}
          >
            {searching ? <span className="spin">⟳</span> : null}
            {searching ? ' Searching…' : 'Search'}
          </button>
        </div>

        {/* top-k selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <span className="text-muted" style={{ fontSize: 12 }}>Top-k:</span>
          {[5, 10, 20, 50].map(k => (
            <button
              key={k}
              type="button"
              className={`chip ${topK === k ? 'chip-active' : ''}`}
              onClick={() => setTopK(k)}
            >
              {k}
            </button>
          ))}
        </div>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {note && (
        <div className="info-banner">
          <span className="info-icon">ℹ</span>
          {note}
        </div>
      )}

      {/* Results */}
      {searched && results.length === 0 && !error && (
        <div className="empty" style={{ padding: '32px 0' }}>
          <div className="empty-icon">🔍</div>
          <div>No results found.</div>
        </div>
      )}

      {results.length > 0 && (
        <div className="search-results">
          <div className="section-title" style={{ marginBottom: 10 }}>
            {results.length} result{results.length !== 1 ? 's' : ''}
          </div>
          {results.map((item, idx) => {
            const isOpen = expanded.has(item.chunk_id)
            const relScore = maxScore > 0 ? item.score / maxScore : 0
            const docFilename = docMap[item.document_id]?.filename ?? item.document_id.slice(0, 12) + '…'

            return (
              <div key={item.chunk_id} className="result-card">
                <div
                  className="result-header"
                  onClick={() => toggleResult(item.chunk_id)}
                >
                  <span className="result-rank text-dim">#{idx + 1}</span>
                  <div className="result-score-bar">
                    <div
                      className="result-score-fill"
                      style={{ width: `${relScore * 100}%` }}
                    />
                  </div>
                  <span className="result-score mono text-muted">
                    {item.score.toFixed(4)}
                  </span>
                  <span className="result-meta text-muted">
                    {docFilename}
                    {item.pages.length > 0 && ` · p.${item.pages.join(',')}`}
                  </span>
                  <span className="result-expand text-dim">{isOpen ? '▲' : '▼'}</span>
                </div>

                <div className={`result-text ${isOpen ? 'result-text-expanded' : 'result-text-collapsed'}`}>
                  {item.raw_text}
                </div>

                {isOpen && (
                  <div className="result-footer">
                    <span className="text-dim" style={{ fontSize: 10 }}>
                      {item.strategy} · {item.token_count} tok
                    </span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
