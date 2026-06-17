// Strip redacted sentinels and undefined values recursively before sending to the backend.
// The backend echoes secrets as "•••" in config state; sending that back would overwrite
// the real value with the literal placeholder string.
function stripRedacted(v) {
    if (v === '•••' || v === undefined)
        return undefined;
    if (Array.isArray(v)) {
        const cleaned = v.map(stripRedacted).filter(x => x !== undefined);
        return cleaned;
    }
    if (v !== null && typeof v === 'object') {
        const out = {};
        for (const [k, val] of Object.entries(v)) {
            const cleaned = stripRedacted(val);
            if (cleaned !== undefined)
                out[k] = cleaned;
        }
        return out;
    }
    return v;
}
// Base fetch with consistent error handling.
async function request(path, init) {
    const hasBody = init?.body != null;
    const res = await fetch(`/api/v1${path}`, {
        headers: {
            ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
            ...init?.headers,
        },
        ...init,
    });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg = body?.detail ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return res.json();
}
// Multipart form request (for file upload).
async function upload(path, form) {
    const res = await fetch(`/api/v1${path}`, { method: 'POST', body: form });
    if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg = body?.detail ?? `HTTP ${res.status}`;
        throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
    }
    return res.json();
}
// ── Health ─────────────────────────────────────────────────────────────────
export const getHealth = () => request('/health/ping');
// ── Discovery ──────────────────────────────────────────────────────────────
export const getDiscovery = (collectionId) => {
    const qs = collectionId ? `?collection_id=${collectionId}` : '';
    return request(`/discovery${qs}`);
};
// ── Collections ────────────────────────────────────────────────────────────
export const listCollections = () => request('/collections/list');
export const createCollection = (body) => request('/collections/create', {
    method: 'POST',
    body: JSON.stringify(stripRedacted(body)),
});
export const deleteCollection = (id) => request(`/collections/${id}/delete`, { method: 'DELETE' });
// ── Config ─────────────────────────────────────────────────────────────────
export const getConfigState = (collectionId) => request(`/collections/${collectionId}/config/state`);
export const getConfigSchema = (collectionId) => request(`/collections/${collectionId}/config/schema`);
export const getConfigHistory = (collectionId) => request(`/collections/${collectionId}/config/history`);
export const updateConfig = (collectionId, patch, note) => request(`/collections/${collectionId}/config/update`, {
    method: 'POST',
    body: JSON.stringify({ patch: stripRedacted(patch), note }),
});
export const rollbackConfig = (collectionId, version) => request(`/collections/${collectionId}/config/rollback`, {
    method: 'POST',
    body: JSON.stringify({ version }),
});
// ── Documents ──────────────────────────────────────────────────────────────
export const listDocuments = (collectionId, params) => {
    const qs = new URLSearchParams();
    if (params?.limit != null)
        qs.set('limit', String(params.limit));
    if (params?.offset != null)
        qs.set('offset', String(params.offset));
    if (params?.status)
        qs.set('status', params.status);
    if (params?.sort_by)
        qs.set('sort_by', params.sort_by);
    if (params?.sort_order)
        qs.set('sort_order', params.sort_order);
    const q = qs.toString() ? `?${qs}` : '';
    return request(`/collections/${collectionId}/documents/list${q}`);
};
export const getDocument = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}`);
export const ingestDocument = (collectionId, file, metadata) => {
    const form = new FormData();
    form.append('file', file);
    if (metadata && Object.keys(metadata).length > 0) {
        form.append('metadata', JSON.stringify(metadata));
    }
    return upload(`/collections/${collectionId}/documents/ingest`, form);
};
export const updateDocument = (collectionId, docId, metadata, reindex = false) => request(`/collections/${collectionId}/documents/${docId}/update`, {
    method: 'POST',
    body: JSON.stringify({ metadata, reindex }),
});
export const reingestDocument = (collectionId, docId, force = false) => request(`/collections/${collectionId}/documents/${docId}/reingest`, {
    method: 'POST',
    body: JSON.stringify({ force }),
});
export const deleteDocument = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}/delete`, {
    method: 'DELETE',
});
// ── Document files (pre-signed URLs) ───────────────────────────────────────
export const getDocumentOriginal = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}/original`);
export const getDocumentMarkdown = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}/markdown`);
export const getDocumentPdf = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}/pdf`);
// ── Chunks ─────────────────────────────────────────────────────────────────
export const listChunks = (collectionId, docId, params) => {
    const qs = new URLSearchParams();
    if (params?.limit != null)
        qs.set('limit', String(params.limit));
    if (params?.offset != null)
        qs.set('offset', String(params.offset));
    const q = qs.toString() ? `?${qs}` : '';
    return request(`/collections/${collectionId}/documents/${docId}/chunks/list${q}`);
};
export const getChunk = (collectionId, docId, chunkId) => request(`/collections/${collectionId}/documents/${docId}/chunks/${chunkId}`);
export const updateChunk = (collectionId, docId, chunkId, body) => request(`/collections/${collectionId}/documents/${docId}/chunks/${chunkId}/update`, { method: 'POST', body: JSON.stringify(body) });
// ── Document block assets ──────────────────────────────────────────────────
export const getBlockFigure = (collectionId, docId, blockId) => request(`/collections/${collectionId}/documents/${docId}/figures/${encodeURIComponent(blockId)}`);
// ── Pages ──────────────────────────────────────────────────────────────────
export const listPages = (collectionId, docId) => request(`/collections/${collectionId}/documents/${docId}/pages/list`);
export const getPage = (collectionId, docId, pageNumber) => request(`/collections/${collectionId}/documents/${docId}/pages/${pageNumber}`);
export const getPageScreenshotUrl = (collectionId, docId, pageNumber) => `/api/v1/collections/${collectionId}/documents/${docId}/pages/${pageNumber}/screenshot`;
export const reingestPage = (collectionId, docId, pageNumber) => request(`/collections/${collectionId}/documents/${docId}/pages/${pageNumber}/reingest`, { method: 'POST' });
// ── Search ─────────────────────────────────────────────────────────────────
export const searchDocuments = (collectionId, query, opts) => request(`/collections/${collectionId}/documents/search`, {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
});
export const searchWithinDocument = (collectionId, docId, query, opts) => request(`/collections/${collectionId}/documents/${docId}/search`, {
    method: 'POST',
    body: JSON.stringify({ query, ...opts }),
});
