import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Stage S1 block — parsed pages with full per-block detail.
// Each page shows a header row with stats; expanding reveals all IR blocks with type badge,
// id, bbox, text, and (for FIGURE blocks) the figure crop + S2 enrichment data.
// Screenshots are toggled independently with the ⊞ button.
import { useState, useEffect } from 'react';
import { listPages, getPage, getPageScreenshotUrl, getBlockFigure } from '../../../api/client';
import { StageBlock, docStatusToStage } from './StageBlock';
/**
 * Parsed document inspector — per-page block detail with figure crops and enrichment.
 */
export function S1Block({ doc, collectionId }) {
    const [pages, setPages] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [expanded, setExpanded] = useState(new Set());
    const [screenshots, setScreenshots] = useState(new Set());
    const [pageBlocks, setPageBlocks] = useState({});
    const [loadingBlocks, setLoadingBlocks] = useState(new Set());
    const [figureSrcs, setFigureSrcs] = useState({});
    const stageStatus = docStatusToStage(doc.status);
    useEffect(() => {
        if (doc.status === 'done')
            void loadPages();
    }, [doc.id, doc.status]);
    async function loadPages() {
        setLoading(true);
        setError(null);
        try {
            const res = await listPages(collectionId, doc.id);
            setPages(res.pages);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setLoading(false);
        }
    }
    async function loadPageBlocks(pageNum) {
        if (pageBlocks[pageNum])
            return;
        setLoadingBlocks(prev => { const s = new Set(prev); s.add(pageNum); return s; });
        try {
            const res = await getPage(collectionId, doc.id, pageNum);
            setPageBlocks(prev => ({ ...prev, [pageNum]: res.blocks }));
            // Pre-fetch figure crop URLs for FIGURE blocks on this page
            const figures = res.blocks.filter(b => b.type.toLowerCase() === 'figure');
            await Promise.allSettled(figures.map(async (b) => {
                try {
                    const r = await getBlockFigure(collectionId, doc.id, b.id);
                    setFigureSrcs(prev => ({ ...prev, [b.id]: r.url }));
                }
                catch { /* crop may not exist yet (S1 skipped or S2 pending) */ }
            }));
        }
        catch { /* silently ignore page load errors */ }
        finally {
            setLoadingBlocks(prev => { const s = new Set(prev); s.delete(pageNum); return s; });
        }
    }
    function toggleExpanded(pageNum) {
        setExpanded(prev => {
            const s = new Set(prev);
            if (s.has(pageNum)) {
                s.delete(pageNum);
            }
            else {
                s.add(pageNum);
                void loadPageBlocks(pageNum);
            }
            return s;
        });
    }
    function toggleScreenshot(pageNum) {
        setScreenshots(prev => {
            const s = new Set(prev);
            if (s.has(pageNum)) {
                s.delete(pageNum);
            }
            else {
                s.add(pageNum);
            }
            return s;
        });
    }
    const summary = doc.status === 'done'
        ? [
            doc.block_count != null ? `${doc.block_count} blocks` : null,
            doc.page_count != null ? `${doc.page_count} pp` : null,
            doc.language ?? null,
        ].filter(Boolean).join(' · ')
        : undefined;
    return (_jsxs(StageBlock, { title: "S1 \u2014 Parse", summary: summary, status: stageStatus, defaultOpen: doc.status === 'done', children: [doc.status !== 'done' && (_jsx("div", { className: "text-muted", style: { fontSize: 12 }, children: doc.status === 'running' || doc.status === 'pending'
                    ? 'Parsing in progress…'
                    : 'No parse results.' })), error && _jsx("div", { className: "error-banner", children: error }), loading && _jsxs("div", { className: "text-muted", children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading pages\u2026"] }), pages.length > 0 && (_jsx("div", { className: "page-list", children: pages.map(page => (_jsx(PageRow, { page: page, collectionId: collectionId, docId: doc.id, isExpanded: expanded.has(page.page), showScreenshot: screenshots.has(page.page), blocks: pageBlocks[page.page] ?? null, isLoadingBlocks: loadingBlocks.has(page.page), figureSrcs: figureSrcs, onToggleExpand: () => toggleExpanded(page.page), onToggleScreenshot: () => toggleScreenshot(page.page) }, page.page))) }))] }));
}
function PageRow({ page, collectionId, docId, isExpanded, showScreenshot, blocks, isLoadingBlocks, figureSrcs, onToggleExpand, onToggleScreenshot, }) {
    return (_jsxs("div", { className: "page-row", children: [_jsxs("div", { className: "page-row-header", onClick: onToggleExpand, children: [_jsxs("span", { className: "page-num mono", children: ["p.", page.page + 1] }), _jsxs("span", { className: "page-stats", children: [_jsxs("span", { className: "text-muted", children: [page.n_blocks, " blocks"] }), page.n_figures > 0 && _jsxs("span", { className: "text-dim", children: [page.n_figures, " fig"] }), page.n_tables > 0 && _jsxs("span", { className: "text-dim", children: [page.n_tables, " tbl"] }), page.n_chunks > 0 && _jsxs("span", { className: "text-dim", children: [page.n_chunks, " chunks"] })] }), _jsx("button", { type: "button", className: "btn-icon", title: showScreenshot ? 'Hide screenshot' : 'Show page screenshot', onClick: e => { e.stopPropagation(); onToggleScreenshot(); }, children: "\u229E" }), _jsx("span", { className: "chunk-toggle text-dim", children: isExpanded ? '▲' : '▼' })] }), showScreenshot && (_jsx("div", { className: "page-screenshot-wrap fadein", children: _jsx("img", { src: getPageScreenshotUrl(collectionId, docId, page.page), alt: `Page ${page.page + 1}`, className: "page-screenshot", loading: "lazy" }) })), isExpanded && (_jsxs("div", { className: "block-list fadein", children: [isLoadingBlocks && (_jsxs("div", { className: "text-muted", style: { padding: '8px 24px', fontSize: 12 }, children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading blocks\u2026"] })), blocks?.map(block => (_jsx(BlockRow, { block: block, figureSrc: figureSrcs[block.id] }, block.id))), blocks?.length === 0 && (_jsx("div", { className: "text-dim", style: { padding: '8px 24px', fontSize: 11 }, children: "No blocks on this page." }))] }))] }));
}
function BlockRow({ block, figureSrc }) {
    const [open, setOpen] = useState(false);
    const isFigure = block.type.toLowerCase() === 'figure';
    const td = block.type_data;
    const color = typeColor(block.type);
    return (_jsxs("div", { className: "block-row", children: [_jsxs("div", { className: "block-row-header", onClick: () => setOpen(o => !o), children: [_jsx("span", { className: "block-type-badge", style: { background: color + '20', color, borderColor: color + '50' }, children: block.type }), _jsxs("span", { className: "block-id-short mono", children: [block.id.slice(0, 22), "\u2026"] }), block.bbox.length === 4 && (_jsxs("span", { className: "block-bbox", children: ["[", block.bbox.map(v => v.toFixed(2)).join(', '), "]"] })), isFigure && td?.kind != null && (_jsx("span", { className: "tag", style: { fontSize: 10, flexShrink: 0 }, children: String(td.kind) })), _jsx("span", { className: "block-text-preview", children: block.text ? block.text.slice(0, 100) : isFigure ? '(figure)' : '' }), _jsx("span", { className: "chunk-toggle text-dim", children: open ? '▲' : '▼' })] }), open && (_jsxs("div", { className: "block-detail fadein", children: [_jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "id" }), _jsx("span", { className: "mono", style: { fontSize: 10, wordBreak: 'break-all' }, children: block.id })] }), _jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "page (0-idx)" }), _jsx("span", { className: "mono", children: block.page }), _jsx("span", { style: { color: 'var(--text-dim)', margin: '0 8px', fontSize: 10 }, children: "bbox" }), _jsxs("span", { className: "mono", style: { fontSize: 10 }, children: ["[", block.bbox.map(v => v.toFixed(4)).join(', '), "]"] })] }), block.text && (_jsxs("div", { className: "block-detail-row", style: { alignItems: 'flex-start' }, children: [_jsx("span", { className: "block-detail-label", children: "text" }), _jsx("pre", { className: "chunk-pre", style: { flex: 1, margin: 0, maxHeight: 120 }, children: block.text })] })), isFigure && td && (_jsx(FigureDetail, { td: td, figureSrc: figureSrc, blockId: block.id }))] }))] }));
}
function FigureDetail({ td, figureSrc, blockId }) {
    return (_jsxs("div", { className: "figure-detail", children: [figureSrc ? (_jsx("img", { src: figureSrc, alt: `Figure crop ${blockId}`, className: "figure-crop-img", loading: "lazy" })) : (_jsx("span", { className: "text-dim", style: { fontSize: 10 }, children: "crop not available" })), td.kind != null && (_jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "kind" }), _jsx("span", { className: "tag", style: { fontSize: 10 }, children: String(td.kind) })] })), td.relevance != null && (_jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "relevance" }), _jsx("span", { className: "mono", children: Number(td.relevance).toFixed(3) })] })), td.crop_key != null && (_jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "crop_key" }), _jsx("span", { className: "mono text-dim", style: { fontSize: 10, wordBreak: 'break-all' }, children: String(td.crop_key) })] })), td.ocr_text != null && (_jsxs("div", { className: "block-detail-row", style: { alignItems: 'flex-start' }, children: [_jsx("span", { className: "block-detail-label", children: "ocr_text" }), _jsx("pre", { className: "chunk-pre", style: { flex: 1, margin: 0, maxHeight: 80, fontSize: 10 }, children: String(td.ocr_text) })] })), td.description != null && (_jsxs("div", { className: "block-detail-row", style: { alignItems: 'flex-start' }, children: [_jsx("span", { className: "block-detail-label", children: "description" }), _jsx("pre", { className: "chunk-pre", style: { flex: 1, margin: 0, maxHeight: 80, fontSize: 10 }, children: String(td.description) })] })), td.data_table != null && Array.isArray(td.data_table) && (_jsxs("div", { className: "block-detail-row", children: [_jsx("span", { className: "block-detail-label", children: "data_table" }), _jsxs("span", { className: "text-muted", style: { fontSize: 11 }, children: [td.data_table.length, " rows \u00D7", ' ', (td.data_table[0]?.length ?? 0), " cols"] })] }))] }));
}
// ── Helpers ───────────────────────────────────────────────────────────────────
function typeColor(type) {
    switch (type.toLowerCase()) {
        case 'heading': return '#a78bfa';
        case 'paragraph': return '#94a3b8';
        case 'figure': return '#6366f1';
        case 'table': return '#34d399';
        case 'list_item': return '#60a5fa';
        case 'caption': return '#f59e0b';
        case 'code': return '#f97316';
        case 'formula': return '#ec4899';
        case 'header_footer': return '#64748b';
        default: return '#94a3b8';
    }
}
