// ====== Code Summary ======
// DocsToolbar — compact filter/sort bar above the document list.
// Provides a client-side filename text search, a server-side status filter,
// and a server-side sort control.  Rendered only when documents exist.

// ====== Internal Project Imports ======
import type { DocStatus } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

/** Active filter + sort values managed by the toolbar. */
export interface DocsFilters {
  /** Client-side filename search applied over the loaded page. */
  nameFilter: string
  /** Server-side status filter — empty string = all statuses. */
  statusFilter: '' | DocStatus
  /** Server-side sort field. */
  sortBy: string
  /** Server-side sort direction. */
  sortOrder: 'asc' | 'desc'
}

/** Defaults that match the backend's default list ordering. */
export const DEFAULT_DOCS_FILTERS: DocsFilters = {
  nameFilter: '',
  statusFilter: '',
  sortBy: 'created_at',
  sortOrder: 'desc',
}

interface DocsToolbarProps {
  filters: DocsFilters
  onFiltersChange: (filters: DocsFilters) => void
}

// ── Constants ────────────────────────────────────────────────────────────────

const STATUS_OPTIONS: { value: '' | DocStatus; label: string }[] = [
  { value: '',        label: 'All' },
  { value: 'done',    label: 'Done' },
  { value: 'running', label: 'Running' },
  { value: 'error',   label: 'Error' },
  { value: 'pending', label: 'Pending' },
]

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Compact filter/sort toolbar for the document list.
 *
 * Status and sort controls are wired to server-side listDocuments params.
 * The name search is client-side and does not trigger a server round-trip.
 *
 * Args:
 *   filters:         Current active filter and sort values.
 *   onFiltersChange: Called with the updated filters whenever any control changes.
 */
export function DocsToolbar({ filters, onFiltersChange }: DocsToolbarProps) {
  function patch(update: Partial<DocsFilters>) {
    onFiltersChange({ ...filters, ...update })
  }

  return (
    <div className="docs-toolbar">
      {/* Client-side filename search */}
      <input
        className="input docs-toolbar-search"
        type="text"
        placeholder="Filter by filename…"
        value={filters.nameFilter}
        onChange={e => patch({ nameFilter: e.target.value })}
        aria-label="Filter documents by filename"
      />

      {/* Server-side status filter */}
      <select
        className="input select docs-toolbar-select"
        value={filters.statusFilter}
        onChange={e => patch({ statusFilter: e.target.value as DocsFilters['statusFilter'] })}
        aria-label="Filter by status"
      >
        {STATUS_OPTIONS.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>

      {/* Server-side sort — composite value encodes field + direction */}
      <select
        className="input select docs-toolbar-select"
        value={`${filters.sortBy}:${filters.sortOrder}`}
        onChange={e => {
          const [by, order] = e.target.value.split(':') as [string, 'asc' | 'desc']
          patch({ sortBy: by, sortOrder: order })
        }}
        aria-label="Sort order"
      >
        <option value="created_at:desc">Newest first</option>
        <option value="created_at:asc">Oldest first</option>
        <option value="filename:asc">Name A–Z</option>
        <option value="filename:desc">Name Z–A</option>
        <option value="status:asc">Status</option>
      </select>
    </div>
  )
}
