// ====== Code Summary ======
// Generic collapsible stage block used as shell for all pipeline stages.
// Handles expand/collapse, status badge rendering, and spinner for running state.

import { useState } from 'react'
import type { DocStatus } from '../../../api/types'

export type StageStatus = 'done' | 'running' | 'error' | 'pending'

interface Props {
  // Stage label displayed in the header (e.g. "S0 — Storage").
  title: string
  // Short summary shown in the header when collapsed (e.g. "2.1 MB · PDF").
  summary?: string
  status: StageStatus
  // Start expanded by default.
  defaultOpen?: boolean
  children?: React.ReactNode
}

const STATUS_COLORS: Record<StageStatus, string> = {
  done:    'var(--s-done)',
  running: 'var(--s-running)',
  error:   'var(--s-error)',
  pending: 'var(--text-dim)',
}

const STATUS_LABELS: Record<StageStatus, string> = {
  done:    'done',
  running: 'running',
  error:   'error',
  pending: 'pending',
}

/**
 * Maps a DocStatus to a StageStatus for per-stage display.
 */
export function docStatusToStage(status: DocStatus): StageStatus {
  if (status === 'done') return 'done'
  if (status === 'error') return 'error'
  if (status === 'running') return 'running'
  return 'pending'
}

/**
 * Collapsible block for a pipeline stage.
 * Renders a header row with title, summary, and status badge.
 */
export function StageBlock({ title, summary, status, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useState(defaultOpen)

  const blockClass = [
    'stage-block',
    status === 'done'    ? 'stage-block-done'    : '',
    status === 'error'   ? 'stage-block-error'   : '',
    status === 'running' ? 'stage-block-running' : '',
  ].filter(Boolean).join(' ')

  return (
    <div className={blockClass}>
      <div className="stage-header" onClick={() => setOpen(v => !v)}>
        {/* Running spinner */}
        {status === 'running' && (
          <span className="spin" style={{ fontSize: 12, color: 'var(--s-running)' }}>⟳</span>
        )}
        <span className="stage-title">{title}</span>
        {summary && (
          <span className="stage-summary">{summary}</span>
        )}
        {/* Status badge */}
        <span
          className="tag"
          style={{
            color: STATUS_COLORS[status],
            borderColor: STATUS_COLORS[status] + '40',
            background: STATUS_COLORS[status] + '10',
            flexShrink: 0,
          }}
        >
          {STATUS_LABELS[status]}
        </span>
        <span className="stage-chevron">{open ? '▲' : '▼'}</span>
      </div>

      {open && children && (
        <div className="stage-body fadein">
          {children}
        </div>
      )}
    </div>
  )
}
