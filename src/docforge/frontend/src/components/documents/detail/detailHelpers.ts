// ====== Code Summary ======
// Pure formatting/status helpers shared across the DocDetailView sub-tabs:
// file-size and duration formatting, plus status-dot CSS class and status text
// colour mapping.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'

/**
 * Formats a file size in bytes to a human-readable string (KB or MB).
 *
 * Args:
 *   bytes: File size in bytes.
 *
 * Returns:
 *   Formatted string such as "1.2 MB" or "345 KB".
 */
export function formatFileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`
  if (bytes >= 1_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${bytes} B`
}

/**
 * Formats a pipeline duration in milliseconds to a compact string.
 *
 * Args:
 *   ms: Duration in milliseconds, or null/undefined.
 *
 * Returns:
 *   Formatted string such as "2.3s" or "─".
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return '─'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/**
 * Returns the CSS class for the status dot matching a document's pipeline status.
 *
 * Args:
 *   status: Document pipeline status string.
 *
 * Returns:
 *   CSS class string for the dot element.
 */
export function dotClass(status: Document['status']): string {
  switch (status) {
    case 'done':    return 'dot dot-done'
    case 'running': return 'dot dot-running spin'
    case 'error':   return 'dot dot-error'
    default:        return 'dot dot-pending'
  }
}

/**
 * Returns the inline colour for status text labels.
 *
 * Args:
 *   status: Document pipeline status string.
 *
 * Returns:
 *   React CSSProperties with a color rule.
 */
export function statusColor(status: Document['status']): React.CSSProperties {
  switch (status) {
    case 'done':    return { color: 'var(--s-done)' }
    case 'running': return { color: 'var(--s-running)' }
    case 'error':   return { color: 'var(--s-error)' }
    default:        return { color: 'var(--s-pending)' }
  }
}
