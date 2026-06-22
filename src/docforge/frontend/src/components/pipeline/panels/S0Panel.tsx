// ====== Code Summary ======
// Trace panel for S0 — Ingest stage.
// Displays ingestion metadata (filename, format, file size, upload time, language).
// Used inside SlidePanel when a stage node is clicked in trace mode.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import type { StageResult } from '../types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface S0PanelProps {
  /** Runtime result for the S0 stage. */
  stageResult: StageResult
  /** The document being traced. */
  doc: Document
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Format a byte count into a human-readable string.
 *
 * Args:
 *   bytes: Raw file size in bytes.
 *
 * Returns:
 *   Human-readable string such as "1.4 MB".
 */
function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Trace panel for the Ingest stage (S0).
 *
 * Shows storage metadata derived from the document record: filename, MIME
 * format, file size, upload time, language, and optional duration from the
 * stage result.  Layout mirrors the s0-meta-grid used in the inspector panel.
 *
 * Args:
 *   stageResult: Runtime result carrying status and optional duration_ms.
 *   doc:         The fully hydrated document record for this trace.
 */
export function S0Panel({ stageResult, doc }: S0PanelProps) {
  return (
    <div className="stage-panel">
      {/* ── Ingestion metadata ── */}
      <div className="s0-meta-grid">
        <div className="s0-meta-item">
          <span className="s0-meta-label">filename</span>
          <span className="s0-meta-value">{doc.filename}</span>
        </div>
        <div className="s0-meta-item">
          <span className="s0-meta-label">format</span>
          <span className="s0-meta-value">{doc.format.toUpperCase()}</span>
        </div>
        <div className="s0-meta-item">
          <span className="s0-meta-label">size</span>
          <span className="s0-meta-value">{fmtBytes(doc.file_size)}</span>
        </div>
        <div className="s0-meta-item">
          <span className="s0-meta-label">uploaded</span>
          <span className="s0-meta-value">{new Date(doc.created_at).toLocaleString()}</span>
        </div>
        {doc.language && (
          <div className="s0-meta-item">
            <span className="s0-meta-label">language</span>
            <span className="s0-meta-value">{doc.language}</span>
          </div>
        )}
        {doc.pipeline_version && (
          <div className="s0-meta-item">
            <span className="s0-meta-label">pipeline</span>
            <span className="s0-meta-value mono">{doc.pipeline_version}</span>
          </div>
        )}
        <div className="s0-meta-item">
          <span className="s0-meta-label">hash</span>
          <span className="s0-meta-value mono">{doc.source_hash.slice(0, 16)}…</span>
        </div>
      </div>

      {/* ── Stage timing ── */}
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
