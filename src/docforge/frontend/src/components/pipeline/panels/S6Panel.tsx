// ====== Code Summary ======
// Trace panel for S6 — Embed & Index stage.
// Shows Qdrant indexing status, chunk count, embed chain traces, and timing.
// Used inside SlidePanel when a stage node is clicked in trace mode.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChainTraceView } from '../../inspect/ChainTraceView'
import type { StageResult } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface S6PanelProps {
  /** Runtime result for the S6 stage. */
  stageResult: StageResult
  /** The document being traced. */
  doc: Document
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Trace panel for the Embed & Index stage (S6).
 *
 * Shows the Qdrant indexing outcome (chunk count, indexed flag), any embed
 * chain traces from {@link doc.embed_chain_traces}, and wall-clock timing from
 * the stage result.
 *
 * Args:
 *   stageResult: Runtime result carrying status, optional duration_ms, metric, error.
 *   doc:         Fully hydrated document record; embed_chain_traces holds S6 lineage.
 */
export function S6Panel({ stageResult, doc }: S6PanelProps) {
  const embedTraces = doc.embed_chain_traces ?? []

  return (
    <div className="stage-panel">
      {/* ── Indexing summary ── */}
      <div className="s0-meta-grid">
        <div className="s0-meta-item">
          <span className="s0-meta-label">indexed</span>
          <span className="s0-meta-value">
            {doc.indexed
              ? <span style={{ color: 'var(--s-done)' }}>yes</span>
              : <span style={{ color: 'var(--text-dim)' }}>no</span>}
          </span>
        </div>
        {doc.chunk_count != null && (
          <div className="s0-meta-item">
            <span className="s0-meta-label">chunks indexed</span>
            <span className="s0-meta-value mono">{doc.chunk_count}</span>
          </div>
        )}
        {stageResult.duration_ms != null && (
          <div className="s0-meta-item">
            <span className="s0-meta-label">duration</span>
            <span className="s0-meta-value mono">{stageResult.duration_ms} ms</span>
          </div>
        )}
        {stageResult.metric && (
          <div className="s0-meta-item">
            <span className="s0-meta-label">metric</span>
            <span className="s0-meta-value mono">{stageResult.metric}</span>
          </div>
        )}
      </div>

      {/* ── Embed chain traces ── */}
      {embedTraces.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <ChainTraceView
            traces={embedTraces}
            label="Embed chain lineage"
            variant="detailed"
          />
        </div>
      )}

      {/* ── Status notes ── */}
      {!doc.indexed && doc.status === 'done' && (
        <div className="text-muted" style={{ fontSize: 12, marginTop: 10 }}>
          Document processed but not indexed — the vector store may not have been
          reachable during ingestion.
        </div>
      )}

      {stageResult.error && (
        <div className="error-banner" style={{ marginTop: 10 }}>
          {stageResult.error}
        </div>
      )}
    </div>
  )
}
