// ====== Code Summary ======
// ResultScore — renders the relevance of a single search result in a clear way:
// a relative relevance bar + qualitative label, the raw fusion score (with an
// explanatory tooltip), and an optional "why this rank" line that translates the
// per-vector ranks into human-readable mini-chips. Extracted from ResultCard.

// ── Types ─────────────────────────────────────────────────────────────────────

interface ResultScoreProps {
  /** Raw fusion score (RRF/DBSF) for this result. */
  score: number
  /** Relevance percentage relative to the best score in the current list. */
  relPct: number
  /** Per-vector name → 1-indexed rank in that vector (debug mode only). */
  vectorRanks?: Record<string, number> | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Relevance display for a single search result.
 *
 * Shows three things:
 *   1. A relative relevance bar (width = relPct%) plus a qualitative French
 *      label (Fort / Bon / Moyen / Faible) coloured by relevance tier.
 *   2. The raw fusion score in small mono text, with a tooltip explaining that
 *      the absolute value is not comparable across queries.
 *   3. A "Pourquoi ce rang" line of mini-chips translating each per-vector rank
 *      into a readable label, sorted by ascending rank — when vectorRanks exist.
 *
 * Args:
 *   score:       Raw fusion score.
 *   relPct:      Relevance percentage relative to the best result.
 *   vectorRanks: Optional per-vector rank map (debug mode only).
 */
export function ResultScore({ score, relPct, vectorRanks }: ResultScoreProps) {
  // 1. Map the relative percentage to a qualitative label and colour.
  const { label, color } = scoreLabel(relPct)

  // 2. Build the sorted list of (vector, rank) pairs when ranks are present.
  const ranks = vectorRanks
    ? Object.entries(vectorRanks).sort((a, b) => a[1] - b[1])
    : []

  return (
    <div className="result-score">
      {/* Relevance bar + qualitative label */}
      <div className="search-result-header" style={{ margin: 0 }}>
        <div style={{ flex: 1 }}>
          <div
            className="search-result-score-bar"
            style={{
              width: `${relPct}%`,
              background: `linear-gradient(90deg, ${color}, ${color}88)`,
            }}
          />
        </div>
        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color, minWidth: 32 }}>
          {relPct}%
        </span>
        <span style={{ fontSize: 11, color, minWidth: 48 }}>{label}</span>
        <span
          className="text-dim"
          style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}
          title="Score de fusion (RRF/DBSF) — combine les rangs de chaque vecteur. La valeur absolue n'est pas comparable d'une requête à l'autre ; fie-toi au rang et au % relatif."
        >
          {score.toFixed(4)}
        </span>
      </div>

      {/* "Why this rank" line — per-vector mini-chips, sorted by ascending rank */}
      {ranks.length > 0 && (
        <div className="result-score-why">
          <span className="text-dim" style={{ fontSize: 10 }}>Pourquoi ce rang :</span>
          {ranks.map(([name, rank]) => (
            <span key={name} className="result-score-why-chip">
              {vectorLabel(name)} #{rank}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Map a relative score percentage to a qualitative French label and colour.
 *
 * Args:
 *   pct: Relative score as a percentage (0–100).
 *
 * Returns:
 *   Object with a French label and a CSS color token string.
 */
function scoreLabel(pct: number): { label: string; color: string } {
  if (pct >= 85) return { label: 'Fort',   color: 'var(--s-done)' }
  if (pct >= 65) return { label: 'Bon',    color: 'var(--accent)' }
  if (pct >= 40) return { label: 'Moyen',  color: 'var(--s-running)' }
  return           { label: 'Faible', color: 'var(--text-dim)' }
}

/**
 * Translate a Qdrant vector name into a readable French label.
 *
 * Recognised forms:
 *   - "content_dense"        → "Sémantique"
 *   - "content_bm25"         → "Mots-clés"
 *   - "meta_<field>_dense"   → "<field> (sém.)"
 *   - "meta_<field>_bm25"    → "<field> (mots-clés)"
 * Any unrecognised name is returned unchanged.
 *
 * Args:
 *   name: Raw vector name from the per-result vector_ranks map.
 *
 * Returns:
 *   string: Human-readable French label.
 */
function vectorLabel(name: string): string {
  // 1. Content vectors — the primary chunk text.
  if (name === 'content_dense') return 'Sémantique'
  if (name === 'content_bm25') return 'Mots-clés'

  // 2. Metadata field vectors — "meta_<field>_<kind>".
  if (name.startsWith('meta_')) {
    const dense = name.endsWith('_dense')
    const bm25 = name.endsWith('_bm25')
    if (dense || bm25) {
      const suffix = dense ? '_dense' : '_bm25'
      const field = name.slice('meta_'.length, name.length - suffix.length)
      return `${field} (${dense ? 'sém.' : 'mots-clés'})`
    }
  }

  // 3. Unknown vector name — return as-is.
  return name
}
