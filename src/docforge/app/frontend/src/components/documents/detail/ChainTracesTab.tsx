// ====== Code Summary ======
// ChainTracesTab — renders the full chain-of-fallbacks lineage for a document:
//   1. Parse-stage traces  (chain_traces)   — one entry per stage that ran.
//   2. S6 embed traces     (embed_chain_traces) — one entry per embed batch.
//
// Both trace arrays are passed directly to <ChainTraceView> (detailed variant)
// so the same visual language (stage pill, attempt cards, escalation arrows,
// score bars, cache-hit badges) is reused without duplication.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChainTraceView } from '../../inspect/ChainTraceView'

interface ChainTracesTabProps {
  /** Fully hydrated document record including chain_traces and embed_chain_traces. */
  doc: Document
}

/**
 * Renders the Chain Traces sub-tab for a document detail view.
 *
 * Displays two clearly-labelled sections:
 *   - Parse stage traces (chain_traces): the escalation chain used by S1.
 *   - Embed traces (embed_chain_traces): one trace per batch sent to S6.
 *
 * Both sections delegate rendering to <ChainTraceView> (detailed variant),
 * which already handles cache-hit cards, score bars, escalation arrows, and
 * prominent error display in FAIL attempts.
 *
 * Args:
 *   doc: Fully hydrated document record.
 */
export function ChainTracesTab({ doc }: ChainTracesTabProps) {
  const parseTraces = doc.chain_traces ?? []
  const embedTraces = doc.embed_chain_traces ?? []
  const hasAny      = parseTraces.length > 0 || embedTraces.length > 0

  if (!hasAny) {
    return (
      <div className="empty">
        <div className="empty-icon">&#x26A1;</div>
        <div>No chain traces recorded for this document.</div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          Chain traces are written when S1 (parse) or S6 (embed) runs with a
          provider chain of two or more providers.
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* 1. Parse-stage traces (S1) */}
      {parseTraces.length > 0 && (
        <section>
          <div className="section-title">Parse stage (S1)</div>
          <ChainTraceView traces={parseTraces} variant="detailed" label="" />
        </section>
      )}

      {/* 2. S6 embed traces — each entry is one batch */}
      {embedTraces.length > 0 && (
        <section>
          <div className="section-title-row">
            <div className="section-title">Embed stage (S6)</div>
            <span className="text-dim" style={{ fontSize: 11 }}>
              {embedTraces.length} batch{embedTraces.length !== 1 ? 'es' : ''}
            </span>
          </div>
          <EmbedTraceBatches traces={embedTraces} />
        </section>
      )}
    </div>
  )
}

// ── EmbedTraceBatches: S6 embed entries labelled as batches ──────────────────

import type { ChainTrace } from '../../../api/types'

interface EmbedTraceBatchesProps {
  traces: ChainTrace[]
}

/**
 * Renders each embed ChainTrace as a labelled batch card.
 *
 * S6 fires one embed call per chunk batch, so the trace array may contain
 * many entries.  Each is wrapped in a thin numbered-batch header and then
 * rendered by <ChainTraceView> (compact=false so attempt detail is visible).
 *
 * Args:
 *   traces: Array of embed ChainTrace records, one per batch.
 */
function EmbedTraceBatches({ traces }: EmbedTraceBatchesProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {traces.map((t, i) => (
        <div key={i}>
          {/* Batch label — only shown when there is more than one batch */}
          {traces.length > 1 && (
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-dim)',
                fontFamily: 'var(--font-mono)',
                marginBottom: 4,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              batch {i + 1}/{traces.length}
            </div>
          )}
          <ChainTraceView traces={[t]} variant="detailed" label="" />
        </div>
      ))}
    </div>
  )
}
