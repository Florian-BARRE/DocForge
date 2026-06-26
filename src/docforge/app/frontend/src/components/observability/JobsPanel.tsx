// ====== Code Summary ======
// JobsPanel — paginated DataTable of recent jobs with status filter and per-row
// cancel action. Fetches from GET /api/v1/jobs; cancel triggers a local refresh.

import { useCallback, useEffect, useState } from 'react'
import type { JobResponse } from '../../api/types'
import { cancelJob, listJobs } from '../../api/client'
import { DataTable } from '../ui/primitives/DataTable'
import type { Column } from '../ui/primitives/DataTable'
import { Tag } from '../ui/primitives/Tag'
import type { TagVariant } from '../ui/primitives/Tag'
import { SectionHeader } from '../ui/primitives/SectionHeader'
import { Mono } from '../ui/primitives/Mono'
import { MeterBar } from './MeterBar'
import { relativeTime, shortId } from './utils'

// ── Types ────────────────────────────────────────────────────────────────────

interface JobsPanelProps {
  /** Map from collection_id → display name for label resolution. */
  collectionsMap: Map<string, string>
  /** When set, triggers a data refresh (caller bumps this on SSE events). */
  refreshToken: number
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PAGE_SIZE    = 20
const STATUS_OPTIONS = ['', 'pending', 'running', 'done', 'failed'] as const

// ── Helpers ───────────────────────────────────────────────────────────────────

function statusVariant(status: string): TagVariant {
  if (status === 'done')    return 'done'
  if (status === 'running') return 'running'
  if (status === 'failed' || status === 'error') return 'error'
  return 'default'
}

function isCancellable(status: string): boolean {
  return status === 'pending' || status === 'running'
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Paginated job list with status filter and cancel actions.
 *
 * Fetches via GET /api/v1/jobs using limit/offset pagination.
 * Cancel triggers POST /api/v1/jobs/{id}/cancel then re-fetches the page.
 *
 * Args:
 *   collectionsMap: id → name lookup for the collection column.
 *   refreshToken:   Bumped by parent on SSE events to trigger re-fetch.
 */
export function JobsPanel({ collectionsMap, refreshToken }: JobsPanelProps) {
  const [jobs,       setJobs]       = useState<JobResponse[]>([])
  const [total,      setTotal]      = useState(0)
  const [offset,     setOffset]     = useState(0)
  const [statusFilter, setStatus]   = useState('')
  const [loading,    setLoading]    = useState(true)
  const [cancelling, setCancelling] = useState<Set<string>>(new Set())
  // Surfaced when a cancel genuinely fails (cleared on the next cancel attempt).
  const [cancelError, setCancelError] = useState<string | null>(null)

  const fetchJobs = useCallback(async () => {
    try {
      const res = await listJobs({
        limit: PAGE_SIZE,
        offset,
        status: statusFilter || undefined,
      })
      setJobs(res.jobs)
      setTotal(res.total)
    } catch { /* silently stale */ }
    finally { setLoading(false) }
  }, [offset, statusFilter])

  // Fetch on mount, filter/page change, and SSE refresh.
  useEffect(() => {
    setLoading(true)
    void fetchJobs()
  }, [fetchJobs, refreshToken])

  // Reset to first page when filter changes.
  function handleStatusChange(s: string) {
    setStatus(s)
    setOffset(0)
  }

  async function handleCancel(id: string) {
    setCancelling(prev => new Set(prev).add(id))
    setCancelError(null)
    try {
      await cancelJob(id)
      await fetchJobs()
    } catch (err) {
      // A 404/409 means the job already finished between render and click — benign,
      // and the refetch reflects the real state. Any other failure is surfaced so the
      // user isn't left staring at a Cancel button that silently did nothing.
      const msg = err instanceof Error ? err.message : String(err)
      if (!/\b(404|409)\b/.test(msg)) setCancelError(`Could not cancel job: ${msg}`)
      await fetchJobs()
    }
    finally {
      setCancelling(prev => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const columns: Column<JobResponse>[] = [
    {
      key: 'status',
      header: 'Status',
      width: 80,
      render: row => <Tag variant={statusVariant(row.status)}>{row.status}</Tag>,
    },
    {
      key: 'collection',
      header: 'Collection',
      width: 120,
      render: row => {
        const name = collectionsMap.get(row.collection_id)
        return (
          <Mono size={11} color="var(--text-muted)" title={row.collection_id}>
            {name ?? shortId(row.collection_id)}
          </Mono>
        )
      },
    },
    {
      key: 'document',
      header: 'Document',
      width: 90,
      render: row => (
        <Mono size={11} color="var(--text-muted)" title={row.document_id}>
          {shortId(row.document_id)}
        </Mono>
      ),
    },
    {
      key: 'stage',
      header: 'Stage / Progress',
      render: row => (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Mono size={11} color="var(--text-muted)" style={{ minWidth: 24 }}>
            {row.current_stage ?? '—'}
          </Mono>
          {row.progress > 0 && (
            <MeterBar value={row.progress} color="var(--accent)" width={60} />
          )}
        </div>
      ),
    },
    {
      key: 'attempt',
      header: 'Try',
      width: 36,
      align: 'center',
      render: row => <Mono size={11} color="var(--text-muted)">{row.attempt}</Mono>,
    },
    {
      key: 'created',
      header: 'Created',
      width: 80,
      render: row => (
        <span style={{ fontSize: 11, color: 'var(--text-dim)' }} title={row.created_at}>
          {relativeTime(row.created_at)}
        </span>
      ),
    },
    {
      key: 'error',
      header: 'Error',
      render: row => row.error
        ? <span style={{ fontSize: 11, color: 'var(--s-error)' }} title={row.error}>
            {row.error.slice(0, 60)}{row.error.length > 60 ? '…' : ''}
          </span>
        : <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>—</span>,
    },
    {
      key: 'cancel',
      header: '',
      width: 64,
      align: 'center',
      render: row => isCancellable(row.status)
        ? (
          <button
            className="btn-icon btn-icon-danger"
            onClick={() => { void handleCancel(row.id) }}
            disabled={cancelling.has(row.id)}
            title="Cancel job"
          >
            {cancelling.has(row.id) ? '…' : 'Cancel'}
          </button>
        )
        : null,
    },
  ]

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div>
      <SectionHeader
        action={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{total} total</span>
            <select
              className="input select"
              value={statusFilter}
              onChange={e => handleStatusChange(e.target.value)}
              style={{ fontSize: 11, padding: '2px 24px 2px 8px', width: 'auto' }}
            >
              {STATUS_OPTIONS.map(s => (
                <option key={s} value={s}>{s || 'All statuses'}</option>
              ))}
            </select>
          </div>
        }
      >
        Jobs
      </SectionHeader>

      {cancelError && (
        <div style={{
          fontSize: 11, color: 'var(--s-error)', background: 'var(--surface-raised)',
          border: '1px solid var(--s-error)', borderRadius: 4, padding: '4px 8px', marginBottom: 6,
        }}>
          {cancelError}
        </div>
      )}

      <DataTable
        columns={columns}
        rows={jobs}
        rowKey={row => row.id}
        emptyMessage={loading ? 'Loading…' : 'No jobs found'}
        maxHeight="340px"
      />

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
          gap: 8, marginTop: 6, fontSize: 11, color: 'var(--text-dim)',
        }}>
          <button
            className="btn-icon"
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            disabled={offset === 0}
          >
            Prev
          </button>
          <span>{currentPage} / {totalPages}</span>
          <button
            className="btn-icon"
            onClick={() => setOffset(offset + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= total}
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
