import { jsxs as _jsxs, jsx as _jsx, Fragment as _Fragment } from "react/jsx-runtime";
// ====== Code Summary ======
// Browse mode — two-column layout: collection list on the left, document list on the right.
// Each document row has an "Inspect" button that switches to the Inspect tab.
import { useState, useEffect } from 'react';
import { listCollections, listDocuments } from '../../api/client';
function statusColor(s) {
    if (s === 'done')
        return 'var(--s-done)';
    if (s === 'error')
        return 'var(--s-error)';
    if (s === 'running')
        return 'var(--s-running)';
    return 'var(--text-dim)';
}
function fmtBytes(bytes) {
    if (bytes < 1024)
        return `${bytes} B`;
    if (bytes < 1024 * 1024)
        return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
/**
 * Collection browse view with split-pane layout.
 * Left: collection list. Right: documents for selected collection.
 */
export function BrowseView({ onInspect }) {
    const [collections, setCollections] = useState([]);
    const [collectionsLoading, setCollectionsLoading] = useState(true);
    const [collectionsError, setCollectionsError] = useState(null);
    const [selectedCollection, setSelectedCollection] = useState(null);
    const [docs, setDocs] = useState([]);
    const [docsTotal, setDocsTotal] = useState(0);
    const [docsLoading, setDocsLoading] = useState(false);
    const [docsError, setDocsError] = useState(null);
    const [offset, setOffset] = useState(0);
    const PAGE_SIZE = 50;
    // 1. Load collections on mount.
    useEffect(() => {
        void loadCollections();
    }, []);
    async function loadCollections() {
        setCollectionsLoading(true);
        setCollectionsError(null);
        try {
            const res = await listCollections();
            setCollections(res.collections);
            if (res.collections.length > 0) {
                setSelectedCollection(res.collections[0]);
            }
        }
        catch (err) {
            setCollectionsError(String(err));
        }
        finally {
            setCollectionsLoading(false);
        }
    }
    // 2. Load documents when collection changes.
    useEffect(() => {
        if (selectedCollection) {
            setOffset(0);
            void loadDocs(selectedCollection.id, 0);
        }
    }, [selectedCollection?.id]);
    async function loadDocs(collectionId, off) {
        setDocsLoading(true);
        setDocsError(null);
        try {
            const res = await listDocuments(collectionId, { limit: PAGE_SIZE, offset: off });
            setDocs(res.documents);
            setDocsTotal(res.total);
        }
        catch (err) {
            setDocsError(String(err));
        }
        finally {
            setDocsLoading(false);
        }
    }
    function selectCollection(col) {
        setSelectedCollection(col);
        setDocs([]);
    }
    function prevPage() {
        const newOff = Math.max(0, offset - PAGE_SIZE);
        setOffset(newOff);
        if (selectedCollection)
            void loadDocs(selectedCollection.id, newOff);
    }
    function nextPage() {
        const newOff = offset + PAGE_SIZE;
        if (newOff < docsTotal) {
            setOffset(newOff);
            if (selectedCollection)
                void loadDocs(selectedCollection.id, newOff);
        }
    }
    return (_jsxs("div", { className: "browse-layout", children: [_jsxs("div", { className: "browse-sidebar", children: [_jsxs("div", { className: "browse-sidebar-header", children: ["Collections", !collectionsLoading && (_jsxs("span", { className: "text-dim", style: { marginLeft: 8 }, children: ["(", collections.length, ")"] }))] }), _jsxs("div", { className: "browse-sidebar-list", children: [collectionsLoading && (_jsxs("div", { className: "text-muted", style: { padding: '8px 10px' }, children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading\u2026"] })), collectionsError && (_jsx("div", { className: "error-banner", style: { margin: 6 }, children: collectionsError })), collections.map(col => (_jsx("div", { className: `browse-col-item ${col.id === selectedCollection?.id ? 'browse-col-item-active' : ''}`, onClick: () => selectCollection(col), children: _jsx("span", { className: "browse-col-name", children: col.name }) }, col.id))), !collectionsLoading && collections.length === 0 && (_jsx("div", { className: "text-dim", style: { padding: '8px 10px', fontSize: 12 }, children: "No collections." }))] })] }), _jsx("div", { className: "browse-main", children: !selectedCollection ? (_jsxs("div", { className: "empty", children: [_jsx("div", { className: "empty-icon", children: "\uD83D\uDCC2" }), _jsx("div", { children: "Select a collection to browse its documents." })] })) : (_jsxs(_Fragment, { children: [_jsxs("div", { className: "panel-header", style: { marginBottom: 16 }, children: [_jsx("div", { className: "panel-title", children: selectedCollection.name }), _jsxs("div", { className: "panel-meta text-muted", children: [_jsxs("span", { children: [docsTotal, " documents"] }), _jsx("span", { className: "mono", style: { fontSize: 11 }, children: selectedCollection.pipeline_version })] })] }), docsError && _jsx("div", { className: "error-banner", children: docsError }), docsLoading ? (_jsxs("div", { className: "text-muted", children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading documents\u2026"] })) : docs.length === 0 ? (_jsxs("div", { className: "empty", style: { padding: '32px 0' }, children: [_jsx("div", { className: "empty-icon", children: "\uD83D\uDCC4" }), _jsx("div", { children: "No documents in this collection." })] })) : (_jsx("div", { className: "doc-list", children: docs.map(doc => (_jsxs("div", { className: "doc-row", children: [_jsx("span", { className: "dot", style: { background: statusColor(doc.status) } }), _jsx("span", { className: "doc-name", children: doc.filename }), _jsx("span", { className: "doc-meta text-muted", children: doc.format.toUpperCase() }), _jsx("span", { className: "doc-meta text-dim", children: fmtBytes(doc.file_size) }), doc.page_count != null && (_jsxs("span", { className: "doc-meta text-dim", children: [doc.page_count, " pp"] })), doc.chunk_count != null && (_jsxs("span", { className: "doc-meta text-dim", children: [doc.chunk_count, " chunks"] })), _jsxs("span", { className: "tag", style: {
                                            color: statusColor(doc.status),
                                            borderColor: statusColor(doc.status) + '40',
                                            background: statusColor(doc.status) + '10',
                                            flexShrink: 0,
                                        }, children: [doc.status === 'running' && _jsx("span", { className: "spin", style: { fontSize: 9 }, children: "\u27F3" }), doc.status] }), _jsx("div", { className: "doc-actions", style: { opacity: 1 }, children: _jsx("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11, padding: '2px 8px' }, onClick: () => onInspect(selectedCollection, doc), children: "Inspect \u2192" }) })] }, doc.id))) })), docsTotal > PAGE_SIZE && (_jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10, marginTop: 14 }, children: [_jsx("button", { type: "button", className: "btn", disabled: offset === 0, onClick: prevPage, children: "\u2190 Prev" }), _jsxs("span", { className: "text-muted", style: { fontSize: 12 }, children: [offset + 1, "\u2013", Math.min(offset + PAGE_SIZE, docsTotal), " of ", docsTotal] }), _jsx("button", { type: "button", className: "btn", disabled: offset + PAGE_SIZE >= docsTotal, onClick: nextPage, children: "Next \u2192" })] }))] })) })] }));
}
