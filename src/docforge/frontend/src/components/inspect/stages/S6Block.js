import { jsx as _jsx } from "react/jsx-runtime";
import { StageBlock } from './StageBlock';
/**
 * Index status block.
 * - doc.indexed === true → done (chunks are in Qdrant)
 * - doc.status !== done  → follows doc status
 * - done but not indexed → Qdrant was not reachable for this run
 */
export function S6Block({ doc }) {
    let status;
    let note = '';
    if (doc.status !== 'done') {
        status = doc.status === 'running' ? 'running' : 'pending';
        note = 'Waiting for pipeline to complete.';
    }
    else if (doc.indexed === true) {
        status = 'done';
        note = `${doc.chunk_count ?? '?'} chunks indexed in Qdrant.`;
    }
    else {
        status = 'pending';
        note = 'Chunks not indexed in Qdrant — vector store may not have been reachable during ingestion.';
    }
    return (_jsx(StageBlock, { title: "S6 \u2014 Index", summary: doc.indexed ? `${doc.chunk_count ?? '?'} chunks` : undefined, status: status, defaultOpen: false, children: _jsx("div", { className: "text-muted", style: { fontSize: 12 }, children: note }) }));
}
