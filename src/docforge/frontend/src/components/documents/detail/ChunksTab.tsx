// ====== Code Summary ======
// ChunksTab — thin wrapper that renders the full chunk inspector (ChunkBrowser)
// for the detail view's Chunks sub-tab.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChunkBrowser } from '../../inspect/ChunkBrowser'

interface ChunksTabProps {
  doc: Document
  collectionId: string
}

/**
 * Renders the Chunks sub-tab: the full chunk browser via ChunkBrowser.
 *
 * Args:
 *   doc:          Fully hydrated document record.
 *   collectionId: UUID of the owning collection.
 */
export function ChunksTab({ doc, collectionId }: ChunksTabProps) {
  return <ChunkBrowser doc={doc} collectionId={collectionId} />
}
