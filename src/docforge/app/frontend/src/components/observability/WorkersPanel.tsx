// ====== Code Summary ======
// WorkersPanel — compact card per arq worker showing live heartbeat data:
// status, hostname, current job, counters, process + system meters, and GPU bars.
// Stale workers (last_seen > 30 s) are dimmed with an amber border.

import type { WorkerSummary } from '../../api/types'
import type { DotStatus } from '../ui/primitives/StatusDot'
import { StatusDot } from '../ui/primitives/StatusDot'
import { SectionHeader } from '../ui/primitives/SectionHeader'
import { EmptyState } from '../ui/primitives/EmptyState'
import { Mono } from '../ui/primitives/Mono'
import { MeterBar } from './MeterBar'
import { relativeTime, isStale, meterColor, shortId } from './utils'

// ── Types ────────────────────────────────────────────────────────────────────

interface WorkersPanelProps {
  /** Live worker list from the monitoring endpoint. */
  workers: WorkerSummary[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function toDotStatus(s: string): DotStatus {
  if (s === 'idle')     return 'idle'
  if (s === 'busy')     return 'running'
  if (s === 'starting') return 'pending'
  return 'warning'
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Renders one compact card per arq worker.
 *
 * Card contents:
 *   - Status dot + hostname (mono) + short worker_id
 *   - Current job (short ID or "idle") + jobs_processed + RSS
 *   - System CPU% and RAM% meter bars
 *   - GPU metrics when present (util% + mem_used/mem_total bar per GPU)
 *   - Last-seen relative time; stale → amber border + dim
 *
 * Args:
 *   workers: Worker heartbeat array from the monitoring overview.
 */
export function WorkersPanel({ workers }: WorkersPanelProps) {
  return (
    <div>
      <SectionHeader>Workers ({workers.length})</SectionHeader>
      {workers.length === 0
        ? <EmptyState icon="⚙" message="No workers connected" description="Start an arq worker to see heartbeats here." />
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {workers.map(w => <WorkerCard key={w.worker_id} worker={w} />)}
          </div>
        )
      }
    </div>
  )
}

// ── WorkerCard ────────────────────────────────────────────────────────────────

function WorkerCard({ worker: w }: { worker: WorkerSummary }) {
  const stale  = isStale(w.last_seen)
  const dotSt  = toDotStatus(w.status)

  return (
    <div style={{
      background: 'var(--panel-bg)',
      border: `1px solid ${stale ? 'var(--s-warning)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)',
      padding: '10px 12px',
      opacity: stale ? 0.6 : 1,
      fontSize: 12,
    }}>

      {/* ── Header: dot + hostname + short id ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 7 }}>
        <StatusDot status={dotSt} size={8} title={w.status} />
        <Mono
          size={11}
          color="var(--text)"
          style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}
        >
          {w.hostname}
        </Mono>
        <Mono size={10} color="var(--text-dim)" style={{ flexShrink: 0 }}>
          {shortId(w.worker_id)}
        </Mono>
      </div>

      {/* ── Job / counters row ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8,
        flexWrap: 'wrap', fontSize: 11,
      }}>
        <span style={{ color: 'var(--text-dim)' }}>
          Job:&nbsp;
          <Mono size={11} color={w.current_job_id ? 'var(--s-running)' : 'var(--text-dim)'}>
            {w.current_job_id ? shortId(w.current_job_id) : 'idle'}
          </Mono>
        </span>
        <span style={{ color: 'var(--text-dim)' }}>
          Done:&nbsp;<Mono size={11} color="var(--text-muted)">{w.jobs_processed}</Mono>
        </span>
        <span style={{ color: 'var(--text-dim)' }}>
          RSS:&nbsp;<Mono size={11} color="var(--text-muted)">{w.rss_mb.toFixed(0)} MB</Mono>
        </span>
        <span style={{ marginLeft: 'auto', color: stale ? 'var(--s-warning)' : 'var(--text-dim)', fontSize: 10 }}>
          {relativeTime(w.last_seen)}{stale ? ' · stale' : ''}
        </span>
      </div>

      {/* ── System meters ── */}
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: w.gpu.length ? 6 : 0 }}>
        <Meter label="CPU" pct={w.sys_cpu_pct} />
        <Meter label="RAM" pct={w.sys_ram_pct} />
        <Meter label="Proc" pct={w.cpu_pct} />
      </div>

      {/* ── GPU rows ── */}
      {w.gpu.map(g => {
        const memPct = g.mem_total_mb > 0 ? (g.mem_used_mb / g.mem_total_mb) * 100 : 0
        return (
          <div key={g.index} style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 6 }}>
            <Meter label={`GPU${g.index}`} pct={g.util_gpu_pct} />
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 10, color: 'var(--text-dim)', minWidth: 50 }}>
                GPU{g.index} mem
              </span>
              <MeterBar
                value={g.mem_used_mb}
                max={g.mem_total_mb}
                color={meterColor(memPct)}
                label={`${g.mem_used_mb}/${g.mem_total_mb} MB`}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Inline meter with label ───────────────────────────────────────────────────

function Meter({ label, pct }: { label: string; pct: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 10, color: 'var(--text-dim)', minWidth: 34 }}>{label}</span>
      <MeterBar value={pct} color={meterColor(pct)} />
    </div>
  )
}
