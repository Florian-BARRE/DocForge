// ====== Code Summary ======
// Search tab — PipelineGraph for the search pipeline (config + trace mode), a query
// input with a search button, a query-variants banner (multi_query), and result cards.
// Discovery-driven config panels open in a SlidePanel on node click.

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import { getConfigState, getDiscovery, searchDocuments } from '../../api/client'
import type { ConfigState, DynamicField, SearchResultItem } from '../../api/types'
import { SlidePanel } from '../layout/SlidePanel'
import { PipelineGraph } from '../pipeline/PipelineGraph'
import { StageConfigPanel } from '../pipeline/panels/StageConfigPanel'
import { SEARCH_STAGES } from '../pipeline/search-stages'
import type { StageDefinition, StageResult } from '../pipeline/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchTabProps {
  /** Active collection to search within. */
  collectionId: string
}

/**
 * Lightweight post-search trace metadata derived from the backend debug_info payload.
 * Drives the graph's "trace" mode after a query completes.
 */
interface SearchTraceInfo {
  /** All query strings sent (original + LLM-generated variants). */
  queryVariants: string[]
  /** Whether a reranker was applied after retrieval. */
  reranked: boolean
  /** Number of candidates retrieved before reranking (or final count if no rerank). */
  candidateCount: number
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Search tab — interactive search UI with a discovery-driven pipeline graph.
 *
 * Config mode (before any search):
 *   PipelineGraph renders in "config" mode. Clicking a node opens a SlidePanel
 *   with {@link StageConfigPanel} populated from the discovery endpoint.
 *   The embed node is read-only (provider auto-derived from ingestion config).
 *
 * Trace mode (after a search):
 *   PipelineGraph switches to "trace" mode with per-stage status derived from
 *   the last {@link SearchTraceInfo}.
 *
 * Props:
 *   collectionId: The collection to run searches against.
 */
export function SearchTab({ collectionId }: SearchTabProps) {
  // ── Query state ──────────────────────────────────────────────────────────────

  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResultItem[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  // Track the last submitted query (not the live input value) for result display.
  const lastQueryRef = useRef<string>('')

  // ── Graph / panel state ───────────────────────────────────────────────────────

  const [activeStage, setActiveStage] = useState<StageDefinition | null>(null)
  const [slidePanelOpen, setSlidePanelOpen] = useState(false)

  // ── Discovery state ──────────────────────────────────────────────────────────

  const [dynamicFields, setDynamicFields] = useState<DynamicField[]>([])
  const [configState, setConfigState] = useState<ConfigState | null>(null)

  // ── Trace state ───────────────────────────────────────────────────────────────

  const [lastSearchInfo, setLastSearchInfo] = useState<SearchTraceInfo | null>(null)

  // ── Expanded result cards ────────────────────────────────────────────────────

  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // 1. Fetch discovery fields and config state on mount / collection change.
  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [discoveryResp, cfgState] = await Promise.all([
          getDiscovery(collectionId),
          getConfigState(collectionId),
        ])
        if (cancelled) return

        // Flatten all endpoint dynamic fields into a single list.
        const allFields: DynamicField[] = discoveryResp.endpoints.flatMap(
          e => e.dynamic_fields ?? []
        )
        setDynamicFields(allFields)
        setConfigState(cfgState)
      } catch {
        // Non-fatal — graph will render in empty config state.
      }
    }

    load()
    return () => { cancelled = true }
  }, [collectionId])

  // 2. Refresh config state after a successful save in StageConfigPanel.
  const handleSaved = useCallback(async () => {
    try {
      const updated = await getConfigState(collectionId)
      setConfigState(updated)
    } catch {
      // Silent — the panel already showed a success indicator.
    }
  }, [collectionId])

  // 3. Derive trace stageResults from lastSearchInfo.
  //    Transform is "done" if there were LLM variants (len > 1), "skipped" if not.
  //    Rerank is "done" if reranked, "skipped" if not.
  //    Embed and retrieve are always "done" when lastSearchInfo exists.
  const stageResults: Record<string, StageResult> | undefined = useMemo(() => {
    if (!lastSearchInfo) return undefined
    return {
      transform: {
        status: lastSearchInfo.queryVariants.length > 1 ? 'done' : 'skipped',
        metric: lastSearchInfo.queryVariants.length > 1
          ? `${lastSearchInfo.queryVariants.length} variants`
          : undefined,
      },
      embed: {
        status: 'done',
      },
      retrieve: {
        status: 'done',
        metric: `${lastSearchInfo.candidateCount} results`,
      },
      rerank: {
        status: lastSearchInfo.reranked ? 'done' : 'skipped',
      },
    }
  }, [lastSearchInfo])

  // 4. Graph mode: "trace" after first successful search, "config" before.
  const graphMode: 'config' | 'trace' = lastSearchInfo ? 'trace' : 'config'

  // 5. Stage node click handler.
  function handleStageClick(stage: StageDefinition) {
    setActiveStage(stage)
    setSlidePanelOpen(true)
  }

  // 6. SlidePanel title.
  const slidePanelTitle = activeStage
    ? activeStage.readOnly
      ? `${activeStage.label} — Read Only`
      : `${activeStage.label} Configuration`
    : ''

  // 7. Run search.
  async function handleSearch(e?: React.FormEvent) {
    e?.preventDefault()
    const q = query.trim()
    if (!q || !collectionId) return

    lastQueryRef.current = q
    setIsSearching(true)
    setSearchError(null)

    try {
      const res = await searchDocuments(collectionId, q, { debug: true })
      setResults(res.results)

      // Extract trace metadata from debug_info.
      const variants = (res.debug_info?.query_variants ?? []) as string[]
      const reranked = Boolean(res.debug_info?.reranked ?? false)
      const candidateCount =
        typeof res.debug_info?.candidate_count === 'number'
          ? res.debug_info.candidate_count
          : res.results.length

      setLastSearchInfo({
        queryVariants: variants.length > 0 ? variants : [q],
        reranked,
        candidateCount,
      })
    } catch (err) {
      setSearchError(String(err))
    } finally {
      setIsSearching(false)
    }
  }

  // 8. Toggle expanded state for a result card.
  function toggleResult(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const maxScore = results.length > 0 ? Math.max(...results.map(r => r.score)) : 1

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="search-tab">
      {/* ── Pipeline graph ── */}
      <div className="search-tab-graph">
        <PipelineGraph
          stages={SEARCH_STAGES}
          mode={graphMode}
          stageResults={stageResults}
          activeStageId={activeStage?.id ?? null}
          onStageClick={handleStageClick}
        />
      </div>

      {/* ── Body: query + results ── */}
      <div className="search-tab-body">
        {/* Query input row */}
        <form onSubmit={handleSearch}>
          <div className="search-query-row">
            <input
              className="input search-query-input"
              type="text"
              placeholder="Enter your search query…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              disabled={isSearching}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSearching || !query.trim()}
            >
              {isSearching ? '…' : 'Search'}
            </button>
          </div>
        </form>

        {/* Query variants banner — only when multi_query produced variants */}
        {lastSearchInfo && lastSearchInfo.queryVariants.length > 1 && (
          <div className="search-variants-banner">
            <span className="text-dim" style={{ fontSize: 11 }}>Variants:</span>
            {lastSearchInfo.queryVariants.map((v, i) => (
              <span key={i} className="search-variant-chip">{v}</span>
            ))}
          </div>
        )}

        {/* Error banner */}
        {searchError && (
          <div className="error-banner">{searchError}</div>
        )}

        {/* Empty state */}
        {!isSearching && lastSearchInfo && results.length === 0 && !searchError && (
          <div className="empty" style={{ padding: '32px 0' }}>
            <div className="empty-icon">🔍</div>
            <div>No results found.</div>
          </div>
        )}

        {/* Result cards */}
        {results.length > 0 && (
          <div className="search-results-list">
            {results.map((item, idx) => (
              <ResultCard
                key={item.chunk_id}
                item={item}
                idx={idx}
                maxScore={maxScore}
                query={lastQueryRef.current}
                isOpen={expanded.has(item.chunk_id)}
                onToggle={() => toggleResult(item.chunk_id)}
                isReranked={lastSearchInfo?.reranked ?? false}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Slide panel ── */}
      <SlidePanel
        isOpen={slidePanelOpen}
        title={slidePanelTitle}
        onClose={() => setSlidePanelOpen(false)}
      >
        {activeStage && activeStage.readOnly ? (
          // Read-only message for the embed node.
          <div className="stage-config-empty" style={{ padding: 16 }}>
            Embed provider is auto-derived from the collection's ingestion config
            and cannot be changed here.
          </div>
        ) : activeStage ? (
          <StageConfigPanel
            stage={activeStage}
            collectionId={collectionId}
            dynamicFields={dynamicFields}
            configState={configState}
            onSaved={handleSaved}
          />
        ) : null}
      </SlidePanel>
    </div>
  )
}

// ── ResultCard ────────────────────────────────────────────────────────────────

interface ResultCardProps {
  /** Search result item from the API. */
  item: SearchResultItem
  /** 0-based rank index used for display. */
  idx: number
  /** Highest score in the result list — used to compute relative percentage. */
  maxScore: number
  /** The query string used for term highlighting. */
  query: string
  /** Whether the card body is currently expanded. */
  isOpen: boolean
  /** Called when the user clicks the card to toggle expansion. */
  onToggle: () => void
  /** Whether the results were reranked — shows a badge when true. */
  isReranked: boolean
}

/**
 * Single search result card.
 *
 * Collapsed state shows a score bar, a 120-character content preview, and the
 * document filename.  Expanded state shows the full chunk content plus provenance
 * metadata.  A "reranked" badge is shown on the first card when reranking was active.
 *
 * Args:
 *   item:       The search result item.
 *   idx:        0-based position in the result list.
 *   maxScore:   Highest score in the result set (for relative bar width).
 *   query:      Last submitted query (for term highlighting).
 *   isOpen:     Whether the card is in expanded state.
 *   onToggle:   Click handler to toggle expansion.
 *   isReranked: Whether reranking was applied.
 */
function ResultCard({ item, idx, maxScore, query, isOpen, onToggle, isReranked }: ResultCardProps) {
  const relPct = maxScore > 0 ? Math.round((item.score / maxScore) * 100) : 0
  const { label: scoreQuality, color: scoreColor } = scoreLabel(relPct)
  const preview = item.raw_text.slice(0, 120)

  return (
    <div className="search-result-card" onClick={onToggle}>
      {/* ── Header ── */}
      <div className="search-result-header">
        {/* Rank */}
        <span className="text-dim" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', minWidth: 24 }}>
          #{idx + 1}
        </span>

        {/* Score bar */}
        <div style={{ flex: 1 }}>
          <div
            className="search-result-score-bar"
            style={{ width: `${relPct}%`, background: `linear-gradient(90deg, ${scoreColor}, ${scoreColor}88)` }}
          />
        </div>

        {/* Percentage + quality label */}
        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: scoreColor, minWidth: 32 }}>
          {relPct}%
        </span>
        <span style={{ fontSize: 11, color: scoreColor, minWidth: 48 }}>{scoreQuality}</span>

        {/* Reranked badge — only on first card when reranking was applied */}
        {isReranked && idx === 0 && (
          <span className="search-reranked-badge">reranked</span>
        )}

        {/* Expand/collapse chevron */}
        <span className="text-dim" style={{ fontSize: 10 }}>{isOpen ? '▲' : '▼'}</span>
      </div>

      {/* ── Preview (collapsed) or full content (expanded) ── */}
      {!isOpen && (
        <div className="search-result-preview">
          <HighlightedText text={preview} query={query} />
          {item.raw_text.length > 120 && <span className="text-dim"> …</span>}
        </div>
      )}

      {isOpen && (
        <div className="search-result-expanded">
          <HighlightedText text={item.raw_text} query={query} />
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
            score {item.score.toFixed(4)} · {item.strategy} · {item.token_count} tok
            · {item.chunk_id.slice(0, 8)}…
          </div>
        </div>
      )}
    </div>
  )
}

// ── HighlightedText ───────────────────────────────────────────────────────────

/**
 * Splits text on query terms (>2 chars) and wraps matches in <mark> elements.
 *
 * Uses a capture-group regex split so matched terms land at odd-numbered indices,
 * allowing them to be wrapped without an extra pass.
 *
 * Args:
 *   text:  The raw text to highlight.
 *   query: The search query string — terms shorter than 3 chars are skipped.
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

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Maps a relative score percentage to a qualitative label and color.
 *
 * Args:
 *   pct: Relative score as a percentage (0–100).
 *
 * Returns:
 *   Object with a human-readable label and a CSS color string.
 */
function scoreLabel(pct: number): { label: string; color: string } {
  if (pct >= 85) return { label: 'Strong',   color: 'var(--s-done)' }
  if (pct >= 65) return { label: 'Good',     color: 'var(--accent)' }
  if (pct >= 40) return { label: 'Moderate', color: 'var(--s-running)' }
  return           { label: 'Weak',       color: 'var(--text-dim)' }
}
