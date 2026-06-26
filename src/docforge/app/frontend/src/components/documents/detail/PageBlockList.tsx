// ====== Code Summary ======
// PageBlockList — the block detail list rendered below the page screenshot
// in the expanded page view.  Each block row shows its type badge, id, and
// text preview.  Clicking a row cross-highlights with PageBlockOverlay.
// Expanded state shows figure OCR/VLM text or table cell grid.

// ====== Internal Project Imports ======
import type { BlockInfo } from '../../../api/types'
import { blockTypeColor } from '../../inspect/chunkHelpers'

interface PageBlockListProps {
  /** IR blocks for this page. */
  blocks: BlockInfo[]
  /** Currently highlighted block id (null = none). */
  activeId: string | null
  /** Called with a block id or null to toggle highlight. */
  onBlockActivate: (id: string | null) => void
}

/**
 * Scrollable block detail list below the page screenshot.
 *
 * Each row is a clickable card.  Activating a row cross-highlights the
 * matching overlay box in PageBlockOverlay (via shared activeId state in parent).
 * Expanded rows show:
 *   - figure: OCR text + VLM description fields
 *   - table:  cell grid (up to 5×5) + dimensions
 *   - other:  full block text
 *
 * Args:
 *   blocks:          IR blocks for this page.
 *   activeId:        Currently highlighted block id.
 *   onBlockActivate: Toggle handler.
 */
export function PageBlockList({ blocks, activeId, onBlockActivate }: PageBlockListProps) {
  if (blocks.length === 0) {
    return (
      <div className="text-dim" style={{ fontSize: 12 }}>No blocks on this page.</div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div className="section-title" style={{ marginBottom: 6 }}>
        {blocks.length} block{blocks.length !== 1 ? 's' : ''}
      </div>
      {blocks.map(block => (
        <BlockDetailRow
          key={block.id}
          block={block}
          isActive={activeId === block.id}
          onActivate={() => onBlockActivate(activeId === block.id ? null : block.id)}
        />
      ))}
    </div>
  )
}

// ── BlockDetailRow ────────────────────────────────────────────────────────────

interface BlockDetailRowProps {
  block: BlockInfo
  isActive: boolean
  onActivate: () => void
}

/**
 * One row in the block detail list.
 *
 * Args:
 *   block:     IR block record.
 *   isActive:  Whether this block is currently highlighted.
 *   onActivate: Toggle the active state.
 */
function BlockDetailRow({ block, isActive, onActivate }: BlockDetailRowProps) {
  const color    = blockTypeColor(block.type)
  const td       = (block.type_data ?? {}) as Record<string, unknown>
  const isFigure = block.type.toLowerCase() === 'figure'
  const isTable  = block.type.toLowerCase() === 'table'

  return (
    <div
      className="block-detail-row"
      style={{
        borderColor:  isActive ? color : undefined,
        background:   isActive ? `${color}0f` : undefined,
      }}
      onClick={onActivate}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onActivate() }}
    >
      {/* Summary line */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span
          className="tag"
          style={{ color, borderColor: `${color}50`, background: `${color}15`, fontSize: 9, padding: '1px 5px' }}
        >
          {block.type}
        </span>
        <span className="mono text-dim" style={{ fontSize: 10 }}>
          {block.id.slice(0, 20)}…
        </span>
        {block.text && !isActive && (
          <span
            className="text-muted"
            style={{ fontSize: 11, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {block.text.slice(0, 100)}
          </span>
        )}
        <span className="text-dim" style={{ fontSize: 10, marginLeft: 'auto' }}>
          {isActive ? '▲' : '▼'}
        </span>
      </div>

      {/* Expanded detail */}
      {isActive && (
        <div className="fadein" style={{ marginTop: 8 }}>
          {isFigure && <FigureDetail td={td} />}
          {isTable  && <TableDetail  td={td} />}
          {!isFigure && !isTable && block.text && (
            <pre style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
              {block.text}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

// ── FigureDetail ──────────────────────────────────────────────────────────────

/**
 * Shows OCR text and VLM description for a figure block.
 *
 * Args:
 *   td: The type_data record from the figure block.
 */
function FigureDetail({ td }: { td: Record<string, unknown> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <BlockField
        label="OCR text"
        value={td.ocr_text != null ? String(td.ocr_text) : null}
        emptyNote="No OCR text — provider skipped or produced no output."
      />
      <BlockField
        label="VLM description"
        value={td.description != null ? String(td.description) : null}
        emptyNote="No VLM description — provider skipped or produced no output."
      />
    </div>
  )
}

// ── TableDetail ───────────────────────────────────────────────────────────────

/**
 * Shows a cell-grid preview for a table block.
 *
 * Up to 5 rows × 5 columns are shown; overflow is indicated with counts.
 *
 * Args:
 *   td: The type_data record from the table block.
 */
function TableDetail({ td }: { td: Record<string, unknown> }) {
  const cells = Array.isArray(td.cells) ? (td.cells as string[][]) : []
  const nRows = typeof td.n_rows === 'number' ? td.n_rows : cells.length
  const nCols = typeof td.n_cols === 'number' ? td.n_cols : (cells[0]?.length ?? 0)

  if (cells.length === 0) {
    return <span className="text-dim" style={{ fontSize: 11 }}>No cell data available.</span>
  }

  const PREVIEW_ROWS = 5
  const PREVIEW_COLS = 5
  const displayRows  = cells.slice(0, PREVIEW_ROWS)

  return (
    <div>
      <div className="text-dim" style={{ fontSize: 10, marginBottom: 4, fontFamily: 'var(--font-mono)' }}>
        {nRows} × {nCols} table
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ fontSize: 10, borderCollapse: 'collapse', fontFamily: 'var(--font-mono)' }}>
          <tbody>
            {displayRows.map((row, ri) => (
              <tr key={ri}>
                {row.slice(0, PREVIEW_COLS).map((cell, ci) => (
                  <td
                    key={ci}
                    style={{
                      border: '1px solid var(--border)',
                      padding: '2px 6px',
                      color: 'var(--text-muted)',
                      maxWidth: 140,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {cell}
                  </td>
                ))}
                {row.length > PREVIEW_COLS && (
                  <td style={{ border: '1px solid var(--border)', padding: '2px 6px', color: 'var(--text-dim)' }}>
                    …
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {cells.length > PREVIEW_ROWS && (
          <div className="text-dim" style={{ fontSize: 10, marginTop: 4 }}>
            … {cells.length - PREVIEW_ROWS} more rows
          </div>
        )}
      </div>
    </div>
  )
}

// ── BlockField ────────────────────────────────────────────────────────────────

/**
 * Labeled field showing a text value or an empty-state note.
 *
 * Args:
 *   label:     Field label (e.g. "OCR text").
 *   value:     Field value (null = empty/not produced).
 *   emptyNote: Message shown when value is null or blank.
 */
function BlockField({ label, value, emptyNote }: { label: string; value: string | null; emptyNote: string }) {
  return (
    <div>
      <div style={{
        fontSize: 10, color: 'var(--text-dim)', textTransform: 'uppercase',
        letterSpacing: '0.06em', marginBottom: 3,
      }}>
        {label}
      </div>
      {value && value.trim() ? (
        <pre style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
          {value}
        </pre>
      ) : (
        <span className="text-dim" style={{ fontSize: 11, fontStyle: 'italic' }}>{emptyNote}</span>
      )}
    </div>
  )
}
