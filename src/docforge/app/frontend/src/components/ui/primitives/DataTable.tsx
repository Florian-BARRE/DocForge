// ====== Code Summary ======
// DataTable primitive — dense, sortable-ready table with sticky header.
// Built for maximum information density (cockpit style). All colors from CSS vars.
// Sortable header: pass onSort + sortKey + sortDir to enable column sorting.

import { ReactNode } from 'react'

// ── Types ────────────────────────────────────────────────────────────────────

export interface Column<T> {
  /** Unique column key (used for sorting). */
  key: string
  /** Column header label. */
  header: ReactNode
  /** Render function for a row cell. */
  render: (row: T, idx: number) => ReactNode
  /** Alignment. Defaults to 'left'. */
  align?: 'left' | 'center' | 'right'
  /** Optional fixed column width (px or CSS string). */
  width?: number | string
}

interface DataTableProps<T> {
  /** Column definitions. */
  columns: Column<T>[]
  /** Row data. */
  rows: T[]
  /** Key extractor for React reconciliation. */
  rowKey: (row: T, idx: number) => string | number
  /** Currently sorted column key. */
  sortKey?: string
  /** Sort direction. */
  sortDir?: 'asc' | 'desc'
  /** Called when a sortable header is clicked. */
  onSort?: (key: string) => void
  /** Empty state message rendered when rows is empty. */
  emptyMessage?: ReactNode
  /** Maximum table height before overflow scroll. */
  maxHeight?: number | string
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Dense data table with sticky header and optional column sorting.
 *
 * All visual styling is token-driven via CSS vars. The header is sticky
 * so long tables remain navigable without losing column context.
 *
 * Args:
 *   columns: Column configuration array with render functions.
 *   rows: Data array.
 *   rowKey: Function to derive a unique key per row.
 *   sortKey / sortDir / onSort: Controlled sort state. Pass all three to
 *     enable clickable column headers.
 *   emptyMessage: Content rendered when rows is empty.
 *   maxHeight: CSS max-height for the scroll container.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sortKey,
  sortDir,
  onSort,
  emptyMessage = 'No data',
  maxHeight = '70vh',
  className = '',
}: DataTableProps<T>) {
  return (
    <div
      className={className}
      style={{
        overflowY: 'auto',
        maxHeight,
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        background: 'var(--surface)',
      }}
    >
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 12,
        }}
      >
        {/* ── Sticky header ── */}
        <thead>
          <tr style={{ background: 'var(--surface-raised)', position: 'sticky', top: 0, zIndex: 1 }}>
            {columns.map(col => {
              const isSorted = sortKey === col.key
              const canSort  = !!onSort
              return (
                <th
                  key={col.key}
                  style={{
                    textAlign: col.align ?? 'left',
                    padding: '5px 8px',
                    borderBottom: '1px solid var(--border)',
                    fontWeight: 600,
                    fontSize: 11,
                    color: 'var(--text-dim)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    whiteSpace: 'nowrap',
                    cursor: canSort ? 'pointer' : undefined,
                    userSelect: 'none',
                    width: col.width,
                  }}
                  onClick={canSort ? () => onSort!(col.key) : undefined}
                >
                  {col.header}
                  {isSorted && (
                    <span style={{ marginLeft: 4, color: 'var(--accent)', fontSize: 9 }}>
                      {sortDir === 'asc' ? '▲' : '▼'}
                    </span>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>

        {/* ── Body ── */}
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  padding: '24px',
                  textAlign: 'center',
                  color: 'var(--text-dim)',
                  fontSize: 12,
                }}
              >
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, idx) => (
              <tr
                key={rowKey(row, idx)}
                style={{ borderBottom: '1px solid var(--border)' }}
                className="dt-row"
              >
                {columns.map(col => (
                  <td
                    key={col.key}
                    style={{
                      textAlign: col.align ?? 'left',
                      padding: '5px 8px',
                      color: 'var(--text)',
                      verticalAlign: 'middle',
                    }}
                  >
                    {col.render(row, idx)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
