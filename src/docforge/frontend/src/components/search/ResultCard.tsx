// ====== Code Summary ======
// ResultCard — a single search result card. Collapsed state shows a score bar, a
// short content preview and the document filename; expanded state shows the full
// chunk content plus provenance metadata. Extracted from SearchTab.

// ====== Internal Project Imports ======
import type { SearchResultItem } from '../../api/types'

// ====== Local Project Imports ======
import { HighlightedText } from './HighlightedText'
import { ResultScore } from './ResultScore'

// ── Types ─────────────────────────────────────────────────────────────────────

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

// ── Component ─────────────────────────────────────────────────────────────────

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
export function ResultCard({ item, idx, maxScore, query, isOpen, onToggle, isReranked }: ResultCardProps) {
  const relPct = maxScore > 0 ? Math.round((item.score / maxScore) * 100) : 0
  const preview = item.raw_text.slice(0, 120)

  return (
    <div className="search-result-card" onClick={onToggle}>
      {/* ── Header ── */}
      <div className="search-result-header">
        {/* Rank */}
        <span className="text-dim" style={{ fontSize: 11, fontFamily: 'var(--font-mono)', minWidth: 24 }}>
          #{idx + 1}
        </span>

        {/* Relevance score (bar + label + raw score + per-vector ranks) */}
        <div style={{ flex: 1 }}>
          <ResultScore score={item.score} relPct={relPct} vectorRanks={item.vector_ranks} />
        </div>

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
