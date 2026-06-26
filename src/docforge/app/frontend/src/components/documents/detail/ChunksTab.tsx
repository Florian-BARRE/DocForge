// ====== Code Summary ======
// ChunksTab — thin wrapper that renders the full chunk inspector (ChunkBrowser)
// for the detail view's Chunks sub-tab.  Forwards jumpChunkId (set by the parent
// when the user jumps from in-document search) and canWrite down to ChunkBrowser.

// ====== Internal Project Imports ======
import type { Document } from '../../../api/types'
import { ChunkBrowser } from '../../inspect/ChunkBrowser'

interface ChunksTabProps {
  doc: Document
  collectionId: string
  /**
   * When set, ChunkBrowser filters to this chunk id and opens it.
   * Set by DocDetailView after the user clicks "Go to chunk" in InDocSearch.
   */
  jumpChunkId?: string | null
  /** When false, write-only controls (Edit tab) are hidden. */
  canWrite?: boolean
}

/**
 * Renders the Chunks sub-tab: the full chunk browser via ChunkBrowser.
 *
 * Args:
 *   doc:          Fully hydrated document record.
 *   collectionId: UUID of the owning collection.
 *   jumpChunkId:  Optional chunk id to auto-open after navigation from search.
 *   canWrite:     Whether write actions (chunk edit) are permitted.
 */
export function ChunksTab({ doc, collectionId, jumpChunkId, canWrite }: ChunksTabProps) {
  return (
    <ChunkBrowser
      doc={doc}
      collectionId={collectionId}
      jumpChunkId={jumpChunkId}
      canWrite={canWrite}
    />
  )
}
