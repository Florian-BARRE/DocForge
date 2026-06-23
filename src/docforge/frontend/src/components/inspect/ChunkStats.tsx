// ====== Code Summary ======
// ChunkStats — summary bar showing chunk count, average token length, strategy
// distribution, and a miniature token-length histogram, all computed from
// already-fetched chunks.

// ====== Standard Library Imports ======
import { useMemo } from 'react'

// ====== Internal Project Imports ======
import type { ChunkResponse } from '../../api/types'

const STRATEGY_COLORS: Record<string, string> = {
  text:    '#94a3b8',
  figure:  '#6366f1',
  table:   '#34d399',
  heading: '#a78bfa',
}

const BUCKETS = [
  { label: '<100',    max: 100  },
  { label: '100–200', max: 200  },
  { label: '200–400', max: 400  },
  { label: '400+',    max: Infinity },
]

/**
 * Summary bar showing chunk count, average token length, strategy distribution,
 * and a miniature token-length histogram — all computed from already-fetched chunks.
 *
 * Args:
 *   chunks: The full set of chunks fetched for the document.
 */
export function ChunkStats({ chunks }: { chunks: ChunkResponse[] }) {
  const stats = useMemo(() => {
    if (!chunks.length) return null
    const total = chunks.length
    const avgTokens = Math.round(chunks.reduce((s, c) => s + c.token_count, 0) / total)
    const maxTokens = Math.max(...chunks.map(c => c.token_count))
    const minTokens = Math.min(...chunks.map(c => c.token_count))

    const byStrategy: Record<string, number> = {}
    chunks.forEach(c => { byStrategy[c.strategy] = (byStrategy[c.strategy] ?? 0) + 1 })

    const bucketCounts = BUCKETS.map((b, i) =>
      chunks.filter(c => c.token_count < b.max && (i === 0 || c.token_count >= BUCKETS[i - 1].max)).length,
    )
    const maxBucket = Math.max(...bucketCounts, 1)

    return { total, avgTokens, minTokens, maxTokens, byStrategy, bucketCounts, maxBucket }
  }, [chunks])

  if (!stats) return null

  return (
    <div className="chunk-stats-bar">
      {/* ── Summary row ── */}
      <div className="chunk-stats-summary">
        <span className="chunk-stats-count mono">
          {stats.total} chunk{stats.total !== 1 ? 's' : ''}
        </span>
        <span className="text-dim" style={{ fontSize: 10 }}>·</span>
        <span className="mono text-muted" style={{ fontSize: 11 }}>
          avg {stats.avgTokens} tok
        </span>
        <span className="text-dim" style={{ fontSize: 10 }}>·</span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>
          {stats.minTokens}–{stats.maxTokens} range
        </span>
        <div className="chunk-stats-types">
          {Object.entries(stats.byStrategy).map(([strat, count]) => (
            <span key={strat} className="chunk-stats-pill">
              <span
                className="chunk-stats-dot"
                style={{ background: STRATEGY_COLORS[strat] ?? '#94a3b8' }}
              />
              <span style={{ color: STRATEGY_COLORS[strat] ?? '#94a3b8' }}>
                {count}
              </span>
              <span className="text-dim">{strat}</span>
            </span>
          ))}
        </div>
      </div>

      {/* ── Token histogram ── */}
      <div className="chunk-histogram">
        <span className="text-dim" style={{ fontSize: 9, marginRight: 8, whiteSpace: 'nowrap' }}>
          token dist.
        </span>
        {BUCKETS.map((b, i) => {
          const count = stats.bucketCounts[i]
          const heightPct = Math.round((count / stats.maxBucket) * 100)
          return (
            <div key={b.label} className="chunk-histogram-bucket" title={`${b.label} tok: ${count} chunk${count !== 1 ? 's' : ''}`}>
              <div
                className="chunk-histogram-bar"
                style={{ height: `${Math.max(heightPct, 4)}%` }}
              />
              <span className="chunk-histogram-label">{b.label.split('–')[0].replace('+', '')}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
