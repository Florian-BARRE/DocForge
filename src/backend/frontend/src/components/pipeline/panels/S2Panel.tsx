// ====== Code Summary ======
// Trace panel for S2 — Enrich stage.
// Wraps ChainTraceView to display OCR / VLM / classifier chain attempts.
// Falls back to a brief status display when no chain traces are available.
// Used inside SlidePanel when a stage node is clicked in trace mode.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChainTraceView } from '../../inspect/ChainTraceView'
import type { StageResult } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface S2PanelProps {
  /** Runtime result for the S2 stage. */
  stageResult: StageResult
  /** The document being traced. */
  doc: Document
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Trace panel for the Enrich stage (S2).
 *
 * Renders document-level chain traces (parse / classifier / OCR / VLM) using
 * {@link ChainTraceView}.  Falls back to a status message and raw metric when
 * no chain traces are recorded on the document (e.g. S2 was disabled or the
 * stage skipped all figures).
 *
 * Args:
 *   stageResult: Runtime result carrying status, optional duration_ms, metric, and error.
 *   doc:         Fully hydrated document record; chain_traces holds the S1 parse trace.
 */
export function S2Panel({ stageResult, doc }: S2PanelProps) {
  // Document-level chain traces cover the parse stage and its escalation chain.
  const docTraces = doc.chain_traces ?? []

  return (
    <div className="stage-panel">
      {/* ── Chain trace viewer ── */}
      {docTraces.length > 0 ? (
        <ChainTraceView
          traces={docTraces}
          label="Enrichment chain lineage"
          variant="detailed"
        />
      ) : (
        <div className="text-muted" style={{ fontSize: 12, padding: '8px 0' }}>
          {stageResult.status === 'skipped'
            ? 'S2 was skipped — enrichment is disabled for this collection.'
            : 'No chain traces recorded for this document.'}
        </div>
      )}

      {/* ── Stage timing / metric ── */}
      {stageResult.duration_ms != null && (
        <div className="stage-panel-row" style={{ marginTop: 12 }}>
          <span className="stage-panel-label">duration</span>
          <span className="stage-panel-value mono">{stageResult.duration_ms} ms</span>
        </div>
      )}
      {stageResult.metric && (
        <div className="stage-panel-row">
          <span className="stage-panel-label">metric</span>
          <span className="stage-panel-value mono">{stageResult.metric}</span>
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
