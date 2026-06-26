// ====== Code Summary ======
// ObservabilityDashboard — live cockpit for the monitoring backend (Bricks A/C/D).
// Subscribes ONCE to the global monitoring SSE stream; debounces refetch of
// overview, workers, and jobs on job.updated / stage.progress events.
// Falls back to 4 s polling when the SSE stream errors; polling tears down
// when events resume — mirrors the DocumentsTab pattern.

// ====== Standard Library Imports ======
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import {
  getMonitoringOverview,
  getMonitoringResources,
  listCollections,
  streamMonitoring,
} from '../../api/client'
import type { Collection, MonitoringOverviewResponse, MonitoringResourcesResponse } from '../../api/types'
import { Spinner } from '../ui/primitives/Spinner'
import { OverviewCards } from './OverviewCards'
import { WorkersPanel } from './WorkersPanel'
import { JobsPanel } from './JobsPanel'
import { ResourcesPanel } from './ResourcesPanel'

// ── Constants ─────────────────────────────────────────────────────────────────

const DEBOUNCE_MS    = 500
const FALLBACK_POLL  = 4_000

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Live monitoring cockpit — replaces the ObservabilityStub.
 *
 * Responsibilities:
 *   - Fetches overview, resources, and collections on mount.
 *   - Maintains a single SSE connection to /monitoring/stream; debounces
 *     overview re-fetch on job.updated and stage.progress events.
 *   - Falls back to 4 s polling when SSE errors, tears down when events resume.
 *   - Bumps `refreshToken` to signal JobsPanel to re-fetch its own data.
 *   - Passes a collectionsMap to JobsPanel for collection name resolution.
 */
export function ObservabilityDashboard() {
  const [overview,      setOverview]      = useState<MonitoringOverviewResponse | null>(null)
  const [resources,     setResources]     = useState<MonitoringResourcesResponse | null>(null)
  const [collections,   setCollections]   = useState<Collection[]>([])
  const [initialLoad,   setInitialLoad]   = useState(true)
  // Bumped on each SSE event to propagate refresh signal to JobsPanel.
  const [refreshToken,  setRefreshToken]  = useState(0)

  const esRef       = useRef<EventSource | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Data fetching ──────────────────────────────────────────────────────────

  const fetchOverview = useCallback(async () => {
    try {
      const ov = await getMonitoringOverview()
      setOverview(ov)
      setRefreshToken(t => t + 1)
    } catch { /* silently stale */ }
  }, [])

  const fetchResources = useCallback(async () => {
    try {
      setResources(await getMonitoringResources())
    } catch { /* silently stale */ }
  }, [])

  // 1. Initial snapshot: overview + resources + collections in parallel.
  useEffect(() => {
    Promise.all([
      fetchOverview(),
      fetchResources(),
      listCollections().then(r => setCollections(r.collections)).catch(() => {}),
    ]).finally(() => setInitialLoad(false))
  }, [fetchOverview, fetchResources])

  // 2. SSE stream: debounce refetch on job/stage events; polling fallback on error.
  useEffect(() => {
    const scheduleRefetch = () => {
      // SSE alive — stop polling fallback if one was started.
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      if (debounceRef.current !== null) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => { void fetchOverview() }, DEBOUNCE_MS)
    }

    const startPolling = () => {
      if (pollRef.current !== null) return
      pollRef.current = setInterval(() => { void fetchOverview() }, FALLBACK_POLL)
    }

    const es = streamMonitoring()
    esRef.current = es
    es.addEventListener('job.updated',    scheduleRefetch)
    es.addEventListener('stage.progress', scheduleRefetch)
    es.onerror = startPolling

    return () => {
      es.close()
      esRef.current = null
      if (debounceRef.current !== null) { clearTimeout(debounceRef.current);  debounceRef.current = null }
      if (pollRef.current     !== null) { clearInterval(pollRef.current);     pollRef.current = null }
    }
  }, [fetchOverview])

  // 3. Build collections lookup map for JobsPanel.
  const collectionsMap = useMemo<Map<string, string>>(
    () => new Map(collections.map(c => [c.id, c.name])),
    [collections],
  )

  // ── Render ─────────────────────────────────────────────────────────────────

  if (initialLoad) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10, color: 'var(--text-dim)' }}>
        <Spinner size={16} />
        <span style={{ fontSize: 13 }}>Loading monitoring…</span>
      </div>
    )
  }

  const workers = overview?.workers.workers ?? []

  return (
    <div style={{
      height: '100%',
      overflowY: 'auto',
      padding: '18px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>
      {/* ── Row 1: Overview stat cards ── */}
      <OverviewCards overview={overview} />

      {/* ── Row 2: Workers (left) + Resources (right) ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 16,
        alignItems: 'start',
      }}>
        <div style={{
          background: 'var(--panel-bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '12px 14px',
        }}>
          <WorkersPanel workers={workers} />
        </div>
        <div style={{
          background: 'var(--panel-bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '12px 14px',
        }}>
          <ResourcesPanel resources={resources} />
        </div>
      </div>

      {/* ── Row 3: Jobs table (full width) ── */}
      <div style={{
        background: 'var(--panel-bg)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '12px 14px',
      }}>
        <JobsPanel collectionsMap={collectionsMap} refreshToken={refreshToken} />
      </div>
    </div>
  )
}
