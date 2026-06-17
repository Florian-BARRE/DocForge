import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Search mode — collection picker + hybrid search bar + ranked result list.
// Shows score bars and chunk provenance (doc filename, pages).
import { useState, useEffect } from 'react';
import { listCollections, listDocuments, searchDocuments } from '../../api/client';
/**
 * Hybrid search view. Users pick a collection, enter a query, select top-k,
 * and view ranked chunks with score bars and provenance metadata.
 */
export function SearchView() {
    const [collections, setCollections] = useState([]);
    const [collectionId, setCollectionId] = useState('');
    const [query, setQuery] = useState('');
    const [topK, setTopK] = useState(10);
    const [results, setResults] = useState([]);
    const [docMap, setDocMap] = useState({});
    const [searching, setSearching] = useState(false);
    const [error, setError] = useState(null);
    const [note, setNote] = useState();
    const [searched, setSearched] = useState(false);
    const [expanded, setExpanded] = useState(new Set());
    // 1. Load collections on mount.
    useEffect(() => {
        listCollections()
            .then(res => {
            setCollections(res.collections);
            if (res.collections.length > 0)
                setCollectionId(res.collections[0].id);
        })
            .catch(() => { });
    }, []);
    // 2. Pre-fetch document list for current collection to resolve filenames.
    useEffect(() => {
        if (!collectionId)
            return;
        listDocuments(collectionId, { limit: 200 })
            .then(res => {
            const map = {};
            res.documents.forEach(d => { map[d.id] = d; });
            setDocMap(map);
        })
            .catch(() => { });
    }, [collectionId]);
    // 3. Execute search.
    async function handleSearch(e) {
        e?.preventDefault();
        if (!collectionId || !query.trim())
            return;
        setSearching(true);
        setError(null);
        setResults([]);
        setNote(undefined);
        setSearched(false);
        try {
            const res = await searchDocuments(collectionId, query.trim(), { top_k: topK });
            setResults(res.results);
            setNote(res.note);
            setSearched(true);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setSearching(false);
        }
    }
    function toggleResult(id) {
        setExpanded(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            }
            else {
                next.add(id);
            }
            return next;
        });
    }
    // Compute max score for normalizing the score bar.
    const maxScore = results.length > 0
        ? Math.max(...results.map(r => r.score))
        : 1;
    return (_jsxs("div", { className: "search-view fadein", children: [_jsx("div", { className: "panel-header", children: _jsx("div", { className: "panel-title", children: "Search" }) }), _jsxs("div", { className: "field-row", style: { marginBottom: 14 }, children: [_jsx("span", { className: "field-label", children: "Collection" }), _jsxs("select", { className: "input select", value: collectionId, onChange: e => setCollectionId(e.target.value), style: { maxWidth: 300 }, children: [collections.length === 0 && (_jsx("option", { value: "", children: "No collections" })), collections.map(col => (_jsx("option", { value: col.id, children: col.name }, col.id)))] })] }), _jsxs("form", { onSubmit: handleSearch, children: [_jsxs("div", { className: "search-bar", children: [_jsx("input", { className: "input search-input", type: "text", placeholder: "Search documents\u2026", value: query, onChange: e => setQuery(e.target.value), autoFocus: true }), _jsxs("button", { type: "submit", className: "btn btn-primary", disabled: searching || !collectionId || !query.trim(), children: [searching ? _jsx("span", { className: "spin", children: "\u27F3" }) : null, searching ? ' Searching…' : 'Search'] })] }), _jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }, children: [_jsx("span", { className: "text-muted", style: { fontSize: 12 }, children: "Top-k:" }), [5, 10, 20, 50].map(k => (_jsx("button", { type: "button", className: `chip ${topK === k ? 'chip-active' : ''}`, onClick: () => setTopK(k), children: k }, k)))] })] }), error && _jsx("div", { className: "error-banner", children: error }), note && (_jsxs("div", { className: "info-banner", children: [_jsx("span", { className: "info-icon", children: "\u2139" }), note] })), searched && results.length === 0 && !error && (_jsxs("div", { className: "empty", style: { padding: '32px 0' }, children: [_jsx("div", { className: "empty-icon", children: "\uD83D\uDD0D" }), _jsx("div", { children: "No results found." })] })), results.length > 0 && (_jsxs("div", { className: "search-results", children: [_jsxs("div", { className: "section-title", style: { marginBottom: 10 }, children: [results.length, " result", results.length !== 1 ? 's' : ''] }), results.map((item, idx) => {
                        const isOpen = expanded.has(item.chunk_id);
                        const relScore = maxScore > 0 ? item.score / maxScore : 0;
                        const docFilename = docMap[item.document_id]?.filename ?? item.document_id.slice(0, 12) + '…';
                        return (_jsxs("div", { className: "result-card", children: [_jsxs("div", { className: "result-header", onClick: () => toggleResult(item.chunk_id), children: [_jsxs("span", { className: "result-rank text-dim", children: ["#", idx + 1] }), _jsx("div", { className: "result-score-bar", children: _jsx("div", { className: "result-score-fill", style: { width: `${relScore * 100}%` } }) }), _jsx("span", { className: "result-score mono text-muted", children: item.score.toFixed(4) }), _jsxs("span", { className: "result-meta text-muted", children: [docFilename, item.pages.length > 0 && ` · p.${item.pages.join(',')}`] }), _jsx("span", { className: "result-expand text-dim", children: isOpen ? '▲' : '▼' })] }), _jsx("div", { className: `result-text ${isOpen ? 'result-text-expanded' : 'result-text-collapsed'}`, children: item.raw_text }), isOpen && (_jsx("div", { className: "result-footer", children: _jsxs("span", { className: "text-dim", style: { fontSize: 10 }, children: [item.strategy, " \u00B7 ", item.token_count, " tok"] }) }))] }, item.chunk_id));
                    })] }))] }));
}
