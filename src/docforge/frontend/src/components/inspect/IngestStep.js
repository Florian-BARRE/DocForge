import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Step 3 of Inspect mode — file drop zone + metadata form + polling until done.
// Shows existing docs for the collection so user can click an existing doc directly.
import { useState, useEffect, useRef, useCallback } from 'react';
import { listDocuments, ingestDocument, getDocument, getDiscovery } from '../../api/client';
import { ChoicePicker } from '../ui/ChoicePicker';
/**
 * Drop-zone ingest with discovery-driven metadata form.
 * After submitting: polls getDocument every 2s until status is done or error,
 * then calls onIngested(doc) automatically.
 */
export function IngestStep({ collection, onIngested }) {
    const [file, setFile] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const [metadata, setMetadata] = useState({});
    const [ingesting, setIngesting] = useState(false);
    const [ingestError, setIngestError] = useState(null);
    const [pollingDocId, setPollingDocId] = useState(null);
    const [pollingStatus, setPollingStatus] = useState('');
    const [discovery, setDiscovery] = useState(null);
    const [docs, setDocs] = useState([]);
    const [docsLoading, setDocsLoading] = useState(true);
    const pollRef = useRef(null);
    const fileInputRef = useRef(null);
    // 1. Load existing docs and discovery on mount.
    useEffect(() => {
        void loadDocs();
        void loadDiscovery();
        return () => { if (pollRef.current)
            clearInterval(pollRef.current); };
    }, [collection.id]);
    async function loadDocs() {
        setDocsLoading(true);
        try {
            const res = await listDocuments(collection.id, { limit: 50 });
            setDocs(res.documents);
        }
        catch { /* ignore */ }
        finally {
            setDocsLoading(false);
        }
    }
    async function loadDiscovery() {
        try {
            setDiscovery(await getDiscovery(collection.id));
        }
        catch { /* non-critical */ }
    }
    // 2. Extract metadata dynamic field from ingest_document endpoint.
    const ingestEndpoint = discovery?.endpoints.find(e => e.route_name === 'ingest_document');
    const metaField = ingestEndpoint?.dynamic_fields.find(df => df.field_path === 'metadata' || df.capability === 'metadata_write');
    // 3. Poll getDocument until terminal status.
    const startPolling = useCallback((docId) => {
        setPollingDocId(docId);
        setPollingStatus('pending');
        pollRef.current = setInterval(async () => {
            try {
                const doc = await getDocument(collection.id, docId);
                setPollingStatus(doc.status);
                if (doc.status === 'done' || doc.status === 'error') {
                    if (pollRef.current)
                        clearInterval(pollRef.current);
                    setPollingDocId(null);
                    setIngesting(false);
                    void loadDocs();
                    onIngested(doc);
                }
            }
            catch { /* keep polling */ }
        }, 2000);
    }, [collection.id, onIngested]);
    // 4. Drag-and-drop handlers.
    function handleDrop(e) {
        e.preventDefault();
        setDragOver(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped)
            setFile(dropped);
    }
    function handleFileChange(e) {
        const picked = e.target.files?.[0];
        if (picked)
            setFile(picked);
    }
    // 5. Submit ingest.
    async function handleIngest() {
        if (!file)
            return;
        setIngesting(true);
        setIngestError(null);
        try {
            const meta = Object.keys(metadata).length > 0 ? metadata : undefined;
            const res = await ingestDocument(collection.id, file, meta);
            setFile(null);
            setMetadata({});
            startPolling(res.doc_id);
        }
        catch (err) {
            setIngestError(String(err));
            setIngesting(false);
        }
    }
    const statusColor = (s) => {
        if (s === 'done')
            return 'var(--s-done)';
        if (s === 'error')
            return 'var(--s-error)';
        if (s === 'running')
            return 'var(--s-running)';
        return 'var(--text-muted)';
    };
    const statusLabel = (s) => {
        if (s === 'done')
            return '✓ done';
        if (s === 'error')
            return '✗ error';
        if (s === 'running')
            return '⟳ running';
        return '· pending';
    };
    return (_jsxs("div", { className: "panel fadein", children: [_jsx("div", { className: "panel-header", children: _jsx("div", { className: "panel-title", children: "Ingest document" }) }), _jsxs("div", { className: `dropzone ${dragOver ? 'dropzone-active' : ''}`, onDragOver: e => { e.preventDefault(); setDragOver(true); }, onDragLeave: () => setDragOver(false), onDrop: handleDrop, onClick: () => fileInputRef.current?.click(), children: [file ? (_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10 }, children: [_jsx("span", { children: file.name }), _jsxs("span", { className: "text-muted", style: { fontSize: 11 }, children: ["(", (file.size / 1024 / 1024).toFixed(1), " MB)"] }), _jsx("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11, padding: '2px 6px' }, onClick: e => { e.stopPropagation(); setFile(null); }, children: "\u2715" })] })) : (_jsxs("div", { className: "dropzone-placeholder", children: [_jsx("span", { className: "dropzone-icon", children: "\u2B06" }), _jsx("span", { children: "Drop a file here or click to browse" }), _jsx("span", { className: "text-dim", style: { fontSize: 11 }, children: collection.supported_formats.join(', ') })] })), _jsx("input", { ref: fileInputRef, type: "file", style: { display: 'none' }, onChange: handleFileChange })] }), metaField && (_jsx("div", { style: { marginTop: 14 }, children: _jsx(ChoicePicker, { field: metaField, value: metadata, onChange: v => setMetadata(v), label: "Metadata" }) })), ingestError && _jsx("div", { className: "error-banner", children: ingestError }), pollingDocId && (_jsxs("div", { className: "info-banner", style: { marginTop: 10 }, children: [_jsx("span", { className: "spin", children: "\u27F3" }), "Processing\u2026 status: ", _jsx("span", { style: { color: statusColor(pollingStatus) }, children: pollingStatus })] })), _jsx("div", { className: "row-end", style: { marginTop: 14 }, children: _jsxs("button", { type: "button", className: "btn btn-primary", disabled: !file || ingesting, onClick: handleIngest, children: [ingesting ? _jsx("span", { className: "spin", children: "\u27F3" }) : null, ingesting ? ' Ingesting…' : 'Ingest'] }) }), _jsxs("div", { className: "section", children: [_jsxs("div", { className: "section-title-row", children: [_jsx("div", { className: "section-title", children: "Existing documents" }), _jsx("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11 }, onClick: loadDocs, children: "\u21BB Refresh" })] }), docsLoading ? (_jsxs("div", { className: "text-muted", children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading\u2026"] })) : docs.length === 0 ? (_jsx("div", { className: "empty", style: { padding: '20px 0' }, children: _jsx("div", { className: "text-dim", children: "No documents yet." }) })) : (_jsx("div", { className: "doc-list", children: docs.map(doc => (_jsxs("div", { className: "doc-row doc-row-clickable", onClick: () => onIngested(doc), title: "Click to inspect this document", children: [_jsx("span", { className: "dot", style: {
                                        background: doc.status === 'done' ? 'var(--s-done)'
                                            : doc.status === 'error' ? 'var(--s-error)'
                                                : doc.status === 'running' ? 'var(--s-running)'
                                                    : 'var(--s-pending)',
                                    } }), _jsx("span", { className: "doc-name", children: doc.filename }), _jsxs("span", { className: "doc-meta text-muted", children: [doc.format, doc.page_count ? ` · ${doc.page_count} pp` : ''] }), _jsx("span", { className: "doc-meta mono", style: { fontSize: 11, color: statusColor(doc.status) }, children: statusLabel(doc.status) })] }, doc.id))) }))] })] }));
}
