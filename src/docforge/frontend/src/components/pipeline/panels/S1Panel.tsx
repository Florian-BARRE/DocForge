// ====== Code Summary ======
// Trace panel for S1 — Parse stage.
// Wraps the existing S1Block inspector (per-page block detail) when the document
// is done; falls back to a stat summary when unavailable.
// Used inside SlidePanel when a stage node is clicked in trace mode.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { S1Block } from '../../inspect/stages/S1Block'
import type { StageResult } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface S1PanelProps {
  /** Runtime result for the S1 stage. */
  stageResult: StageResult
  /** Collection the document belongs to. */
  collectionId: string
  /** Document being traced. */
  doc: Document
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Trace panel for the Parse stage (S1).
 *
 * Delegates to {@link S1Block} for full per-page block detail when the document
 * status is "done".  When the pipeline has not yet completed, shows a concise
 * status message derived from the stage result instead.
 *
 * Args:
 *   stageResult:   Runtime result carrying status, optional duration_ms and metric.
 *   collectionId:  Collection identifier passed to the S1Block sub-component.
 *   doc:           Fully hydrated document record for this trace.
 */
export function S1Panel({ stageResult, collectionId, doc }: S1PanelProps) {
  return (
    <div className="stage-panel">
      {/* ── Full S1 inspector when the document is ready ── */}
      <S1Block doc={doc} collectionId={collectionId} />

      {/* ── Stage timing ── */}
      {stageResult.duration_ms != null && (
        <div className="stage-panel-row" style={{ marginTop: 8 }}>
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
