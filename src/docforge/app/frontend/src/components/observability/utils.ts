// ====== Code Summary ======
// Shared helpers for the Observability dashboard components.
// Pure utility functions — no React, no state, no I/O.

// ── Time ──────────────────────────────────────────────────────────────────────

/**
 * Converts an ISO timestamp into a human-readable "X ago" string.
 *
 * Args:
 *   iso: ISO 8601 date string.
 *
 * Returns:
 *   A short relative-time string, e.g. "12s ago", "4m ago", "2h ago".
 */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1_000)
  if (s < 60)    return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60)    return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24)    return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/**
 * Returns true when `last_seen` is stale (more than `thresholdMs` ago).
 * Used to dim worker cards that may have disconnected.
 *
 * Args:
 *   iso:         ISO timestamp string.
 *   thresholdMs: Staleness threshold in milliseconds. Defaults to 30 s.
 */
export function isStale(iso: string | null | undefined, thresholdMs = 30_000): boolean {
  if (!iso) return true
  return Date.now() - new Date(iso).getTime() > thresholdMs
}

// ── Meter colors ──────────────────────────────────────────────────────────────

/**
 * Returns a CSS variable for a meter bar based on the given percentage.
 *
 * Thresholds:  < 60% → green (done), 60–85% → warning, > 85% → error.
 * All values are CSS vars (token-driven).
 *
 * Args:
 *   pct: Percentage value between 0 and 100.
 */
export function meterColor(pct: number): string {
  if (pct >= 85) return 'var(--s-error)'
  if (pct >= 60) return 'var(--s-warning)'
  return 'var(--s-done)'
}

// ── ID formatting ─────────────────────────────────────────────────────────────

/**
 * Shortens a UUID to its first 8 characters for dense display.
 *
 * Args:
 *   id: Full UUID string.
 */
export function shortId(id: string | null | undefined): string {
  if (!id) return '—'
  return id.slice(0, 8)
}
