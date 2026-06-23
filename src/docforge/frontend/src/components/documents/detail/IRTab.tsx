// ====== Code Summary ======
// IRTab — thin wrapper that renders the per-page IR block inspector (S1Block)
// inside the detail view's stage panel.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { S1Block } from '../../inspect/stages/S1Block'

interface IRTabProps {
  doc: Document
  collectionId: string
}

/**
 * Renders the IR sub-tab: the per-page block inspector via S1Block.
 *
 * Args:
 *   doc:          Fully hydrated document record.
 *   collectionId: UUID of the owning collection.
 */
export function IRTab({ doc, collectionId }: IRTabProps) {
  return (
    <div className="stage-panel" style={{ padding: 0 }}>
      <S1Block doc={doc} collectionId={collectionId} />
    </div>
  )
}
