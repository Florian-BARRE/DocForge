// ====== Code Summary ======
// Stage S0 block — shows storage metadata: hash, format, file size, created_at.
// Always present once a document is loaded.

import type { Document } from '../../../api/types'
import { StageBlock } from './StageBlock'

interface Props {
  doc: Document
  collectionId: string
}

function fmtBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/**
 * Storage metadata block for a document.
 * Status is always "done" — if we have a Document, it was stored successfully.
 */
export function S0Block({ doc }: Props) {
  return (
    <StageBlock
      title="S0 — Storage"
      summary={`${fmtBytes(doc.file_size)} · ${doc.format.toUpperCase()}`}
      status="done"
      defaultOpen={true}
    >
      <div className="s0-meta-grid">
        <div className="s0-meta-item">
          <span className="s0-meta-label">hash</span>
          <span className="s0-meta-value mono">{doc.source_hash.slice(0, 16)}…</span>
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
          <span className="s0-meta-label">created</span>
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
      </div>

      {/* User metadata */}
      {Object.keys(doc.user_meta ?? {}).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div className="section-title">User metadata</div>
          <div className="s0-meta-grid">
            {Object.entries(doc.user_meta).map(([k, v]) => (
              <div key={k} className="s0-meta-item">
                <span className="s0-meta-label">{k}</span>
                <span className="s0-meta-value">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pipeline errors */}
      {doc.pipeline_errors && doc.pipeline_errors.length > 0 && (
        <div className="error-banner" style={{ marginTop: 10 }}>
          {doc.pipeline_errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
    </StageBlock>
  )
}
