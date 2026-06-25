// ====== Code Summary ======
// JobsTab — renders the full job history for a document: ingestion + reingestions
// + retries, newest-first.
//
// Each job row shows:
//   status pill · attempt label (ingestion / re-ingestion N) · current_stage
//   · progress % · worker_id · created_at · wall-clock duration
//   · expandable error text (when present)
//   · arq_status badge (when present and different from status)

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import type { Document, JobResponse, JobStatus } from '../../../api/types'

interface JobsTabProps {
  /** Fully hydrated document record including the jobs array. */
  doc: Document
}

// ── Status pill colours (read from CSS custom properties) ─────────────────────

function statusStyle(status: JobStatus): React.CSSProperties {
  switch (status) {
    case 'done':    return { background: 'rgba(34, 197, 94, 0.14)',  color: 'var(--s-done)',    border: '1px solid rgba(34,197,94,0.28)' }
    case 'running': return { background: 'rgba(217, 119, 6, 0.14)',  color: 'var(--s-running)', border: '1px solid rgba(217,119,6,0.28)' }
    case 'failed':  return { background: 'rgba(239, 68, 68, 0.14)',  color: 'var(--s-error)',   border: '1px solid rgba(239,68,68,0.28)' }
    default:        return { background: 'rgba(148, 163, 184, 0.14)', color: 'var(--s-pending)', border: '1px solid rgba(148,163,184,0.28)' }
  }
}

// ── Duration helper ───────────────────────────────────────────────────────────

/**
 * Computes a human-readable duration between two ISO timestamps.
 *
 * Args:
 *   from: ISO-8601 start timestamp.
 *   to:   ISO-8601 end timestamp, or null if the job is still in progress.
 *
 * Returns:
 *   Formatted string such as "3.2s" or "2m 14s", or "─" when from is null.
 */
function durationBetween(from: string | null, to: string | null): string {
  if (!from) return '─'
  const start = new Date(from).getTime()
  const end   = to ? new Date(to).getTime() : Date.now()
  const ms    = end - start
  if (ms < 1000)   return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60_000)
  const s = Math.round((ms % 60_000) / 1000)
  return `${m}m ${s}s`
}

// ── Single job row ─────────────────────────────────────────────────────────────

interface JobRowProps {
  job: JobResponse
  /** Ordinal label: 1 = "Ingestion", 2+ = "Re-ingestion N". */
  ordinal: number
}

/**
 * Renders a single job as a collapsible card row.
 *
 * The card header is always visible.  When the job has an error message,
 * clicking the row expands a full-text error block so no information is
 * truncated.
 *
 * Args:
 *   job:     The job record to render.
 *   ordinal: Display order — 1 is the initial ingestion, 2+ are re-ingestions.
 */
function JobRow({ job, ordinal }: JobRowProps) {
  const [expanded, setExpanded] = useState(false)
  const hasError   = Boolean(job.error)
  const isClickable = hasError

  // Label shown in the attempt column
  const attemptLabel = ordinal === 1 ? 'Ingestion' : `Re-ingestion ${ordinal - 1}`

  // Duration: prefer finished_at, fall back to now for running jobs
  const duration = durationBetween(job.started_at, job.finished_at)

  // Whether to show the arq_status badge — skip when it would duplicate status
  const showArqStatus = job.arq_status != null && job.arq_status !== job.status

  return (
    <div
      className="jobs-tab-row"
      style={{ borderColor: job.status === 'failed' ? 'rgba(239,68,68,0.30)' : undefined }}
    >
      {/* ── Row header ── */}
      <div
        className={`jobs-tab-row-header${isClickable ? ' jobs-tab-row-clickable' : ''}`}
        onClick={isClickable ? () => setExpanded(e => !e) : undefined}
        role={isClickable ? 'button' : undefined}
        tabIndex={isClickable ? 0 : undefined}
        onKeyDown={isClickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') setExpanded(v => !v) } : undefined}
        aria-expanded={isClickable ? expanded : undefined}
      >
        {/* Status pill */}
        <span className="jobs-tab-status-pill" style={statusStyle(job.status)}>
          {job.status}
        </span>

        {/* Attempt / ingestion label */}
        <span className="jobs-tab-attempt mono">{attemptLabel}</span>

        {/* Current stage (running only) */}
        {job.current_stage && (
          <span className="jobs-tab-stage text-dim">
            {job.current_stage}
          </span>
        )}

        {/* Progress bar (running or if present) */}
        {job.progress > 0 && job.status !== 'done' && (
          <div className="jobs-tab-progress-wrap" title={`${job.progress}%`}>
            <div
              className="jobs-tab-progress-fill"
              style={{ width: `${Math.min(100, job.progress)}%` }}
            />
          </div>
        )}
        {job.progress > 0 && job.status !== 'done' && (
          <span className="text-dim" style={{ fontSize: 10, flexShrink: 0 }}>{job.progress}%</span>
        )}

        {/* Spacer */}
        <span style={{ flex: 1 }} />

        {/* arq status badge when different */}
        {showArqStatus && (
          <span className="jobs-tab-arq-badge">arq: {job.arq_status}</span>
        )}

        {/* Duration */}
        <span className="text-dim" style={{ fontSize: 11, flexShrink: 0, minWidth: 42, textAlign: 'right' }}>
          {duration}
        </span>

        {/* Worker */}
        {job.worker_id && (
          <span className="mono text-dim" style={{ fontSize: 10, flexShrink: 0, maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {job.worker_id.slice(0, 8)}
          </span>
        )}

        {/* Created timestamp */}
        <span className="text-dim" style={{ fontSize: 10, flexShrink: 0, whiteSpace: 'nowrap' }}>
          {new Date(job.created_at).toLocaleString()}
        </span>

        {/* Expand chevron when there is an error */}
        {hasError && (
          <span className="text-dim" style={{ fontSize: 10, flexShrink: 0 }}>
            {expanded ? '▲' : '▼'}
          </span>
        )}
      </div>

      {/* ── Expanded error block ── */}
      {expanded && job.error && (
        <div className="jobs-tab-error-body">
          <pre className="jobs-tab-error-pre">{job.error}</pre>
        </div>
      )}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

/**
 * Renders the Jobs sub-tab showing the full job history for a document.
 *
 * Jobs are displayed newest-first (the backend already returns them in that
 * order).  The oldest job is labelled "Ingestion"; subsequent ones are
 * "Re-ingestion N" so the user can immediately tell how many times the
 * document was reprocessed.
 *
 * Args:
 *   doc: Fully hydrated document record.  The jobs field is optional; an
 *        empty-state message is shown when absent or empty.
 */
export function JobsTab({ doc }: JobsTabProps) {
  const jobs = doc.jobs ?? []

  if (jobs.length === 0) {
    return (
      <div className="empty">
        <div className="empty-icon">&#x1F4CB;</div>
        <div>No job history available for this document.</div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>
          Job records are attached when the document is ingested or re-ingested.
        </div>
      </div>
    )
  }

  // Jobs arrive newest-first from the backend.  The ordinal label is built by
  // computing the logical index against the total: the oldest job (last in
  // array) is ordinal 1 (ingestion), each newer one increments.
  const total = jobs.length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Summary row */}
      <div style={{ marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {total} job{total !== 1 ? 's' : ''} total
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>·</span>
        <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>newest first</span>
      </div>

      {/* Job rows */}
      <div className="jobs-tab-list">
        {jobs.map((job, idx) => (
          <JobRow
            key={job.id}
            job={job}
            // newest-first: idx 0 is the latest attempt (ordinal = total),
            // idx total-1 is the first ingestion (ordinal = 1)
            ordinal={total - idx}
          />
        ))}
      </div>
    </div>
  )
}
