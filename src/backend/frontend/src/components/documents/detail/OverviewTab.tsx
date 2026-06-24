// ====== Code Summary ======
// OverviewTab — renders a two-column key/value grid of all available document
// metadata, including user_meta / implicit_meta fields and any pipeline errors.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'

// ====== Local Project Imports ======
import { formatDuration, formatFileSize } from './detailHelpers'

interface OverviewTabProps {
  doc: Document
  pipelineDurationMs: number | null | undefined
}

/**
 * Renders a two-column key/value grid of all available document metadata.
 *
 * Args:
 *   doc:                 Fully hydrated document record.
 *   pipelineDurationMs:  Pipeline wall-clock time cast from the raw response.
 */
export function OverviewTab({ doc, pipelineDurationMs }: OverviewTabProps) {
  // 1. Build the list of rows from known document fields.
  const rows: Array<{ label: string; value: string }> = []

  const push = (label: string, value: string | null | undefined) => {
    if (value != null && value !== '') rows.push({ label, value })
  }

  push('ID', doc.id)
  push('Collection', doc.collection_id)
  push('Filename', doc.filename)
  push('Format', doc.format)
  push('File size', String(doc.file_size != null ? formatFileSize(doc.file_size) : null))
  push('Status', doc.status)
  push('Language', doc.language)
  push('Page count', doc.page_count != null ? String(doc.page_count) : null)
  push('Block count', doc.block_count != null ? String(doc.block_count) : null)
  push('Chunk count', doc.chunk_count != null ? String(doc.chunk_count) : null)
  push('Indexed', doc.indexed ? 'Yes' : 'No')
  push('Pipeline version', doc.pipeline_version)
  push('Pipeline duration', pipelineDurationMs != null ? formatDuration(pipelineDurationMs) : null)
  push('Quality score', doc.quality_score != null ? doc.quality_score.toFixed(3) : null)
  push('Source hash', doc.source_hash)
  push('Created at', doc.created_at ? new Date(doc.created_at).toLocaleString() : null)
  push('Has original', doc.has_original ? 'Yes' : 'No')
  push('Has markdown', doc.has_markdown ? 'Yes' : 'No')
  push('Has PDF', doc.has_pdf ? 'Yes' : 'No')

  // 2. Append any user_meta fields.
  if (doc.user_meta && typeof doc.user_meta === 'object') {
    for (const [k, v] of Object.entries(doc.user_meta)) {
      if (v != null) push(`user_meta.${k}`, String(v))
    }
  }

  // 3. Append any implicit_meta fields.
  if (doc.implicit_meta && typeof doc.implicit_meta === 'object') {
    for (const [k, v] of Object.entries(doc.implicit_meta)) {
      if (v != null) push(`implicit_meta.${k}`, String(v))
    }
  }

  // 4. Show pipeline errors if any.
  const errors = doc.pipeline_errors ?? []

  return (
    <div>
      {/* Metadata grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: '4px 16px', padding: '4px 0' }}>
        {rows.map(({ label, value }) => (
          <div key={label} style={{ display: 'contents' }}>
            <span className="stage-panel-label" style={{ minWidth: 180 }}>{label}</span>
            <span className="stage-panel-value mono" style={{ wordBreak: 'break-all', fontSize: 12 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Pipeline errors */}
      {errors.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <div className="stage-panel-label" style={{ marginBottom: 6 }}>Pipeline errors</div>
          {errors.map((e, i) => (
            <div key={i} className="error-banner" style={{ marginBottom: 4, fontSize: 11 }}>{e}</div>
          ))}
        </div>
      )}
    </div>
  )
}
