// ====== Code Summary ======
// Search playground — interactive hybrid search with configurable search pipeline
// (query transform strategy + reranker), visible weight sliders, auto-search when
// parameters change, and query-term highlighting in results.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Collection, Document, SearchResultItem } from '../../api/types'
import { getConfigState, listCollections, listDocuments, searchDocuments } from '../../api/client'
import {
  DEFAULT_SEARCH_PIPELINE,
  SearchPipelinePanel,
} from './SearchPipelinePanel'
import type { SearchPipelineCfg } from './SearchPipelinePanel'

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

  // Embed provider of the selected collection — drives the provider badge.
  const [embedProviderId, setEmbedProviderId] = useState<string>('tei')

  // Search pipeline configuration — synced with the collection's stored config.
  const [pipelineConfig, setPipelineConfig] = useState<SearchPipelineCfg>(DEFAULT_SEARCH_PIPELINE)

  // Query variants returned by multi_query transform — populated from debug_info.
  const [queryVariants, setQueryVariants] = useState<string[]>([])

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

  // 3. Fetch collection config state — derives the embed provider badge and loads
  //    the stored search pipeline configuration (query transform + reranker).
  useEffect(() => {
    if (!collectionId) return
    getConfigState(collectionId)
      .then(cfg => {
        setEmbedProviderId(cfg.embed_provider_id ?? 'tei')
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const searchCfg = (cfg as any).pipeline?.search
        if (searchCfg) setPipelineConfig(searchCfg as SearchPipelineCfg)
        else setPipelineConfig(DEFAULT_SEARCH_PIPELINE)
        setQueryVariants([])
      })
      .catch(() => {
        setEmbedProviderId('tei')
        setPipelineConfig(DEFAULT_SEARCH_PIPELINE)
      })
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
        weights: { content_dense: dense, content_bm25: sparse },
        debug: true,
      })
      setResults(res.results)
      setNote(res.note ?? undefined)
      setSearched(true)
      // Extract query variants from debug_info — populated by multi_query transform.
      const variants = (res.debug_info?.query_variants ?? []) as string[]
      setQueryVariants(variants.length > 1 ? variants : [])
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
      <div className="field-row" style={{ marginBottom: 8 }}>
        <span className="field-label">Collection</span>
        <select
          className="input select"
          value={collectionId}
          onChange={e => {
            setCollectionId(e.target.value)
            setSearched(false)
            setResults([])
            setQueryVariants([])
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

      {/* ── Embed provider badge ── */}
      {collectionId && (
        <div className="field-row" style={{ marginBottom: 14 }}>
          <span className="field-label" />
          <EmbedProviderBadge providerId={embedProviderId} />
        </div>
      )}

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

      {/* ── Search Pipeline panel ── */}
      {collectionId && (
        <SearchPipelinePanel
          collectionId={collectionId}
          initialConfig={pipelineConfig}
          onConfigChange={setPipelineConfig}
        />
      )}

      {/* ── Query variants banner (multi_query) ── */}
      {queryVariants.length > 1 && (
        <div className="query-variants-banner">
          <span className="query-variants-label">Query variants ({queryVariants.length})</span>
          <div className="query-variants-list">
            {queryVariants.map((v, i) => (
              <span key={i} className="query-variant-chip">{v}</span>
            ))}
          </div>
        </div>
      )}

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
              {pipelineConfig.rerank.enabled && (
                <span className="pipeline-badge pipeline-badge-rerank">reranked</span>
              )}
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

// ── EmbedProviderBadge ───────────────────────────────────────────────────────

/** Human-readable labels and colours per embed provider discriminator. */
const PROVIDER_META: Record<string, { label: string; color: string }> = {
  tei:           { label: 'TEI · BGE-M3 (local)',   color: '#6366f1' },
  openai_compat: { label: 'OpenAI-compat (local)',   color: '#10b981' },
  openai:        { label: 'OpenAI (external API)',   color: '#f59e0b' },
}

/**
 * Pill badge showing which embed provider was used for this collection.
 * Helps users understand which search backend will be queried.
 */
function EmbedProviderBadge({ providerId }: { providerId: string }) {
  const meta = PROVIDER_META[providerId] ?? { label: providerId, color: '#6b7280' }
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '2px 8px', borderRadius: 999,
        background: meta.color + '18', border: `1px solid ${meta.color}40`,
        fontSize: 11, color: meta.color, fontFamily: 'var(--font-mono)',
      }}
      title="Embed provider used during ingestion — search uses the same model"
    >
      <span style={{ opacity: 0.7 }}>embed:</span>
      {meta.label}
    </span>
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
            {item.vector_ranks && <VectorRankPills ranks={item.vector_ranks} />}
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

// ── VectorRankPills ──────────────────────────────────────────────────────────

/**
 * Renders per-vector rank breakdown as pills (e.g. "dense-text #1" "sparse-text #4").
 * Absent vectors are shown grayed out as "#—" to signal the chunk didn't appear in
 * that vector's candidate list before RRF fusion.
 */
const KNOWN_VECTORS = ['content_dense', 'content_bm25'] as const

function VectorRankPills({ ranks }: { ranks: Record<string, number> }) {
  // Merge known vectors with any extra per-field vectors from the collection schema
  const allVectors = [
    ...KNOWN_VECTORS,
    ...Object.keys(ranks).filter(k => !KNOWN_VECTORS.includes(k as typeof KNOWN_VECTORS[number])),
  ]
  return (
    <div className="vector-rank-pills">
      {allVectors.map(vec => {
        const rank = ranks[vec]
        const isMiss = rank === undefined
        // Short label: strip "content_" prefix → "dense" / "bm25" / per-field suffix
        const short = vec.replace(/^content_/, '')
        return (
          <span
            key={vec}
            className={`vector-rank-pill${isMiss ? ' vector-rank-miss' : ''}`}
            title={`${vec}: ${isMiss ? 'not in candidate list' : `ranked #${rank}`}`}
          >
            {short} {isMiss ? '#—' : `#${rank}`}
          </span>
        )
      })}
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function scoreLabel(pct: number): { label: string; color: string } {
  if (pct >= 85) return { label: 'Strong', color: 'var(--s-done)' }
  if (pct >= 65) return { label: 'Good',   color: 'var(--accent)' }
  if (pct >= 40) return { label: 'Moderate', color: 'var(--s-running)' }
  return           { label: 'Weak',     color: 'var(--text-dim)' }
}
