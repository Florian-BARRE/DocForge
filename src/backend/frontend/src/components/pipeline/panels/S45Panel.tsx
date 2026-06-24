// ====== Code Summary ======
// Trace panel for S4/S5 — Chunk and Contextualize stages.
// Wraps the full ChunkBrowser component for rich chunk inspection.
// Used inside SlidePanel when a stage node is clicked in trace mode.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChunkBrowser } from '../../inspect/ChunkBrowser'
import type { StageResult } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface S45PanelProps {
  /** Runtime result for the S4 or S5 stage. */
  stageResult: StageResult
  /** Collection the document belongs to. */
  collectionId: string
  /** Document being traced. */
  doc: Document
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Trace panel for the Chunk and Contextualize stages (S4 / S5).
 *
 * Delegates to {@link ChunkBrowser} for full chunk inspection: token histogram,
 * strategy breakdown, per-chunk raw/embed text diff, IR block detail, and
 * provenance tree.
 *
 * Args:
 *   stageResult:   Runtime result carrying status, optional duration_ms, metric, error.
 *   collectionId:  Collection identifier forwarded to ChunkBrowser.
 *   doc:           Fully hydrated document record for this trace.
 */
export function S45Panel({ stageResult, collectionId, doc }: S45PanelProps) {
  return (
    <div className="stage-panel">
      {/* ── Full chunk browser ── */}
      <ChunkBrowser doc={doc} collectionId={collectionId} />

      {/* ── Stage timing / metric ── */}
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
