// ====== Code Summary ======
// Stage S6 block — shows embedding / Qdrant index status.
// Derives status from doc.indexed flag.

import type { Document } from '../../../api/types'
import { StageBlock } from './StageBlock'
import type { StageStatus } from './StageBlock'

interface Props {
  doc: Document
  collectionId: string
}

/**
 * Index status block.
 * - doc.indexed === true → done (chunks are in Qdrant)
 * - doc.status !== done  → follows doc status
 * - done but not indexed → Qdrant was not reachable for this run
 */
export function S6Block({ doc }: Props) {
  let status: StageStatus
  let note = ''

  if (doc.status !== 'done') {
    status = doc.status === 'running' ? 'running' : 'pending'
    note = 'Waiting for pipeline to complete.'
  } else if (doc.indexed === true) {
    status = 'done'
    note = `${doc.chunk_count ?? '?'} chunks indexed in Qdrant.`
  } else {
    status = 'pending'
    note = 'Chunks not indexed in Qdrant — vector store may not have been reachable during ingestion.'
  }

  return (
    <StageBlock
      title="S6 — Index"
      summary={doc.indexed ? `${doc.chunk_count ?? '?'} chunks` : undefined}
      status={status}
      defaultOpen={false}
    >
      <div className="text-muted" style={{ fontSize: 12 }}>{note}</div>
    </StageBlock>
  )
}
