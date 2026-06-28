// ====== Code Summary ======
// OverviewCards — a row of five stat cards summarising the current monitoring snapshot.
// Shows: queue depth, throughput/min, running jobs, done jobs, and worker count.
// All colors from CSS vars (token-driven).

import type { MonitoringOverviewResponse } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface OverviewCardsProps {
  /** Latest overview snapshot, or null while loading. */
  overview: MonitoringOverviewResponse | null
}

// ── Sub-component ─────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string | number
  /** Secondary sub-label rendered below the value. */
  sub?: string
  /** Highlight color for the value (CSS var or literal). Defaults to text. */
  color?: string
}

/**
 * Dense numeric stat card for the overview row.
 *
 * Args:
 *   label: Card heading (uppercase, dimmed).
 *   value: Primary metric value.
 *   sub:   Optional secondary line.
 *   color: Optional color for the value text.
 */
function StatCard({ label, value, sub, color = 'var(--text)' }: StatCardProps) {
  return (
    <div style={{
      flex: 1,
      minWidth: 100,
      background: 'var(--panel-bg)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '10px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}>
      <span style={{
        fontSize: 10,
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        color: 'var(--text-dim)',
      }}>
        {label}
      </span>
      <span style={{
        fontSize: 22,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        color,
        lineHeight: 1.1,
      }}>
        {value}
      </span>
      {sub && (
        <span style={{
          fontSize: 10,
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-mono)',
        }}>
          {sub}
        </span>
      )}
    </div>
  )
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Horizontal row of five stat cards summarising queue, jobs, and worker state.
 *
 * Renders placeholder dashes when overview is null (initial load or error).
 *
 * Args:
 *   overview: Latest monitoring overview snapshot.
 */
export function OverviewCards({ overview }: OverviewCardsProps) {
  const q        = overview?.queue
  const w        = overview?.workers
  const running  = q?.counts?.['running'] ?? 0
  const done     = q?.counts?.['done']    ?? 0
  const depth    = q?.queue_depth         ?? 0
  const tpm      = q?.throughput_per_min  ?? 0
  const wCount   = w?.count               ?? 0

  return (
    <div style={{
      display: 'flex',
      gap: 10,
      flexWrap: 'wrap',
    }}>
      <StatCard
        label="Queue depth"
        value={overview ? depth : '—'}
        color={depth > 0 ? 'var(--s-warning)' : 'var(--text)'}
      />
      <StatCard
        label="Throughput"
        value={overview ? `${tpm.toFixed(1)}` : '—'}
        sub={q ? `per min · ${q.window_minutes}m window` : undefined}
        color="var(--accent)"
      />
      <StatCard
        label="Running"
        value={overview ? running : '—'}
        color={running > 0 ? 'var(--s-running)' : 'var(--text)'}
      />
      <StatCard
        label="Done"
        value={overview ? done : '—'}
        sub={q ? `last ${q.window_minutes}m` : undefined}
        color={done > 0 ? 'var(--s-done)' : 'var(--text)'}
      />
      <StatCard
        label="Workers"
        value={overview ? wCount : '—'}
        color={wCount > 0 ? 'var(--text)' : 'var(--text-dim)'}
      />
    </div>
  )
}
