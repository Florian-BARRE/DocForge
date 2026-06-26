// ====== Code Summary ======
// PageBlockOverlay — renders a page screenshot with IR block bounding boxes
// overlaid as positioned, color-coded divs (cross-highlighted with the block list).
// IR bboxes are NORMALIZED [x0, y0, x1, y1] in [0,1], so they map directly to
// percentages of the displayed image — independent of the server-side 2× zoom and
// of any browser resize. Clicking a box highlights the matching list row and back.

// ====== Third-Party / React Imports ======
import type { CSSProperties } from 'react'

// ====== Internal Project Imports ======
import type { BlockInfo } from '../../../api/types'
import { blockTypeColor } from '../../inspect/chunkHelpers'

interface PageBlockOverlayProps {
  /** IR blocks from getPage(). */
  blocks: BlockInfo[]
  /** Screenshot URL (PNG, includes bearer ?token= query param). */
  screenshotUrl: string
  /** Currently highlighted block id — controlled by parent for cross-highlight. */
  activeId: string | null
  /** Called when a bbox box is clicked. */
  onBlockActivate: (id: string | null) => void
}

/**
 * Overlays IR block bounding boxes on a page screenshot.
 *
 * Bboxes are normalized fractions [x0, y0, x1, y1] in [0,1] (top-left origin),
 * so the box is placed/sized as a percentage of the container — which spans the
 * full displayed image — making it correct at any rendered size or zoom.
 *
 * Args:
 *   blocks:          IR block records for this page.
 *   screenshotUrl:   Token-authorised PNG URL.
 *   activeId:        Block id currently highlighted (null = none).
 *   onBlockActivate: Click handler — called with the block id or null to clear.
 */
export function PageBlockOverlay({
  blocks, screenshotUrl, activeId, onBlockActivate,
}: PageBlockOverlayProps) {
  // Build the CSS position style for one normalized bbox.
  function boxStyle(bbox: number[], color: string, isActive: boolean): CSSProperties {
    if (bbox.length < 4) return { display: 'none' }
    return {
      position: 'absolute',
      left:    `${bbox[0] * 100}%`,
      top:     `${bbox[1] * 100}%`,
      width:   `${Math.max(0, bbox[2] - bbox[0]) * 100}%`,
      height:  `${Math.max(0, bbox[3] - bbox[1]) * 100}%`,
      border:  `2px solid ${color}`,
      background: isActive ? `${color}55` : `${color}1a`,
      boxSizing: 'border-box',
      borderRadius: 2,
      cursor: 'pointer',
      transition: 'background 0.12s',
      pointerEvents: 'auto',
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      {/* Page screenshot */}
      <img
        src={screenshotUrl}
        alt="Page screenshot"
        style={{
          width: '100%',
          display: 'block',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border)',
        }}
      />

      {/* Block bbox overlays — normalized coords map straight to % of the image */}
      {blocks.map(block => {
        const color    = blockTypeColor(block.type)
        const isActive = activeId === block.id
        return (
          <div
            key={block.id}
            style={boxStyle(block.bbox, color, isActive)}
            title={`${block.type}  ·  ${block.id.slice(0, 24)}`}
            onClick={() => onBlockActivate(isActive ? null : block.id)}
          />
        )
      })}
    </div>
  )
}
