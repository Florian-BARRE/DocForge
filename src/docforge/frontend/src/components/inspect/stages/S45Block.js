import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Stage S4/S5 block — shows chunks with their raw_text, embed_text, and provenance.
// Each chunk is collapsed by default; click to expand raw_text / embed_text tabs.
import { useState, useEffect } from 'react';
import { listChunks, getBlockFigure } from '../../../api/client';
import { StageBlock, docStatusToStage } from './StageBlock';
/**
 * Chunk list for S4/S5 stages.
 * Loads up to 200 chunks on mount when doc is done.
 */
export function S45Block({ doc, collectionId }) {
    const [chunks, setChunks] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    // Set of expanded chunk ids.
    const [expanded, setExpanded] = useState(new Set());
    // Active text tab per chunk: 'raw' | 'embed'
    const [textTab, setTextTab] = useState({});
    // Presigned URL cache for figure chunks: chunkId → url
    const [figureSrcs, setFigureSrcs] = useState({});
    const stageStatus = docStatusToStage(doc.status);
    useEffect(() => {
        if (doc.status === 'done')
            void loadChunks();
    }, [doc.id, doc.status]);
    async function loadChunks() {
        setLoading(true);
        setError(null);
        try {
            const res = await listChunks(collectionId, doc.id, { limit: 200 });
            setChunks(res.chunks);
            setTotal(res.total);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setLoading(false);
        }
    }
    async function fetchFigureSrc(chunk) {
        if (figureSrcs[chunk.id] !== undefined)
            return;
        if (chunk.strategy !== 'figure' || chunk.block_ids.length === 0)
            return;
        try {
            const r = await getBlockFigure(collectionId, doc.id, chunk.block_ids[0]);
            setFigureSrcs(prev => ({ ...prev, [chunk.id]: r.url }));
        }
        catch {
            // Crop not available yet — store empty string to avoid retry on re-open
            setFigureSrcs(prev => ({ ...prev, [chunk.id]: '' }));
        }
    }
    function toggleChunk(id, chunk) {
        setExpanded(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            }
            else {
                next.add(id);
                void fetchFigureSrc(chunk);
            }
            return next;
        });
    }
    function getTab(id) {
        return textTab[id] ?? 'raw';
    }
    function setTab(id, tab) {
        setTextTab(prev => ({ ...prev, [id]: tab }));
    }
    // Extract pages from prov object.
    function getPages(chunk) {
        const prov = chunk.prov;
        const pages = prov?.pages;
        if (Array.isArray(pages))
            return pages;
        return [];
    }
    function getHeadingPath(chunk) {
        const prov = chunk.prov;
        return typeof prov?.heading_path === 'string' ? prov.heading_path : null;
    }
    const summary = doc.status === 'done'
        ? `${doc.chunk_count ?? total} chunks${chunks[0]?.strategy ? ` · ${chunks[0].strategy}` : ''}`
        : undefined;
    return (_jsxs(StageBlock, { title: "S4/S5 \u2014 Chunks", summary: summary, status: stageStatus, defaultOpen: false, children: [doc.status !== 'done' && (_jsx("div", { className: "text-muted", style: { fontSize: 12 }, children: doc.status === 'running' || doc.status === 'pending'
                    ? 'Chunking in progress…'
                    : 'No chunks.' })), error && _jsx("div", { className: "error-banner", children: error }), loading && _jsxs("div", { className: "text-muted", children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading chunks\u2026"] }), total > 200 && (_jsxs("div", { className: "info-banner", children: [_jsx("span", { className: "info-icon", children: "\u2139" }), "Showing first 200 of ", total, " chunks."] })), chunks.length > 0 && (_jsx("div", { className: "chunk-list", children: chunks.map((chunk, idx) => {
                    const isOpen = expanded.has(chunk.id);
                    const pages = getPages(chunk);
                    const headingPath = getHeadingPath(chunk);
                    const tab = getTab(chunk.id);
                    return (_jsxs("div", { className: `chunk-card ${isOpen ? 'chunk-card-expanded' : ''}`, children: [_jsxs("div", { className: "chunk-header", onClick: () => toggleChunk(chunk.id, chunk), children: [_jsxs("span", { className: "chunk-rank text-dim mono", children: ["#", idx + 1] }), pages.length > 0 && (_jsxs("span", { className: "chunk-pages text-muted", children: ["[p.", pages.join(','), "]"] })), _jsx("span", { className: "chunk-strategy", children: chunk.strategy }), _jsxs("span", { className: "chunk-tok text-dim", children: [chunk.token_count, " tok"] }), _jsx("span", { className: "chunk-preview text-muted", children: chunk.raw_text.slice(0, 120) }), _jsx("span", { className: "chunk-toggle text-dim", children: isOpen ? '▲' : '▼' })] }), isOpen && (_jsxs("div", { className: "chunk-detail fadein", children: [headingPath && (_jsx("div", { className: "chunk-breadcrumb mono", children: headingPath })), chunk.strategy === 'figure' && (_jsx("div", { className: "chunk-figure-preview", children: figureSrcs[chunk.id] ? (_jsx("img", { src: figureSrcs[chunk.id], alt: "Figure crop", className: "figure-crop-img", loading: "lazy" })) : figureSrcs[chunk.id] === '' ? (_jsx("span", { className: "text-dim", style: { fontSize: 10 }, children: "crop not available" })) : (_jsxs("span", { className: "text-dim", style: { fontSize: 10 }, children: [_jsx("span", { className: "spin", children: "\u27F3" }), " loading\u2026"] })) })), _jsxs("div", { className: "chunk-text-tabs", children: [_jsx("button", { type: "button", className: `chunk-text-tab ${tab === 'raw' ? 'chunk-text-tab-active' : ''}`, onClick: () => setTab(chunk.id, 'raw'), children: "raw_text" }), _jsx("button", { type: "button", className: `chunk-text-tab ${tab === 'embed' ? 'chunk-text-tab-active' : ''}`, onClick: () => setTab(chunk.id, 'embed'), children: "embed_text" })] }), _jsx("pre", { className: "chunk-pre", children: tab === 'raw' ? chunk.raw_text : chunk.embed_text }), _jsxs("div", { className: "chunk-footer", children: [chunk.block_ids.length > 0 && (_jsxs("span", { className: "text-dim", style: { fontSize: 10 }, children: ["blocks: ", chunk.block_ids.slice(0, 4).join(', '), chunk.block_ids.length > 4 ? '…' : ''] })), chunk.parent_id && (_jsxs("span", { className: "text-dim", style: { fontSize: 10 }, children: ["parent: ", chunk.parent_id.slice(0, 8), "\u2026"] }))] })] }))] }, chunk.id));
                }) }))] }));
}
