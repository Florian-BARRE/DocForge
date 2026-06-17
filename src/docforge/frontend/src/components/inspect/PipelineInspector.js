import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
// ====== Code Summary ======
// Step 4 of Inspect mode — full pipeline inspector for a selected document.
// Header: filename + status badges + download buttons + inline markdown viewer toggle.
// Body: S0/S1/S2/S45/S6 stage blocks. Polls while pending/running.
import { useState, useEffect, useRef, useCallback } from 'react';
import { getDocument, getDocumentOriginal, getDocumentMarkdown, getDocumentPdf, getBlockFigure, reingestDocument, } from '../../api/client';
import { S0Block } from './stages/S0Block';
import { S1Block } from './stages/S1Block';
import { S45Block } from './stages/S45Block';
import { S6Block } from './stages/S6Block';
import { StageBlock } from './stages/StageBlock';
/**
 * Pipeline inspector — polls until terminal status, then renders all stage blocks.
 * Includes an inline IR Markdown viewer that fetches the presigned URL on demand.
 */
export function PipelineInspector({ collection, initialDoc, onBack }) {
    const [doc, setDoc] = useState(initialDoc);
    const [downloading, setDownloading] = useState(null);
    const [reingesting, setReingesting] = useState(false);
    const [error, setError] = useState(null);
    const [markdownText, setMarkdownText] = useState(null);
    const [markdownFigures, setMarkdownFigures] = useState({});
    const [showMarkdown, setShowMarkdown] = useState(false);
    const [loadingMarkdown, setLoadingMarkdown] = useState(false);
    const pollRef = useRef(null);
    const stopPoll = useCallback(() => {
        if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
        }
    }, []);
    // 1. Sync with latest initialDoc when it changes.
    useEffect(() => {
        setDoc(initialDoc);
    }, [initialDoc.id]);
    // 2. Auto-poll while running / pending.
    useEffect(() => {
        if (doc.status === 'running' || doc.status === 'pending') {
            stopPoll();
            pollRef.current = setInterval(async () => {
                try {
                    const updated = await getDocument(collection.id, doc.id);
                    setDoc(updated);
                    if (updated.status !== 'running' && updated.status !== 'pending')
                        stopPoll();
                }
                catch { /* keep polling */ }
            }, 2000);
        }
        else {
            stopPoll();
        }
        return stopPoll;
    }, [doc.id, doc.status, collection.id, stopPoll]);
    // 3. Download / open in new tab.
    async function handleDownload(kind) {
        setDownloading(kind);
        setError(null);
        try {
            let res;
            if (kind === 'original')
                res = await getDocumentOriginal(collection.id, doc.id);
            else if (kind === 'pdf')
                res = await getDocumentPdf(collection.id, doc.id);
            else
                res = await getDocumentMarkdown(collection.id, doc.id);
            window.open(res.url, '_blank');
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setDownloading(null);
        }
    }
    // 4. Inline markdown viewer — fetch content once, resolve figure refs, toggle display.
    async function handleViewMarkdown() {
        if (showMarkdown) {
            setShowMarkdown(false);
            return;
        }
        if (markdownText) {
            setShowMarkdown(true);
            return;
        }
        setLoadingMarkdown(true);
        setError(null);
        try {
            const { url } = await getDocumentMarkdown(collection.id, doc.id);
            const resp = await fetch(url);
            if (!resp.ok)
                throw new Error(`HTTP ${resp.status}`);
            const text = await resp.text();
            setMarkdownText(text);
            // Resolve figure refs: our serializer emits ![fig:{blockId}](fig:{blockId})
            const FIG_RE = /!\[fig:([^\]]+)\]\(fig:[^\)]+\)/g;
            const blockIds = [...new Set([...text.matchAll(FIG_RE)].map(m => m[1]))];
            const urls = {};
            await Promise.allSettled(blockIds.map(async (blockId) => {
                try {
                    const r = await getBlockFigure(collection.id, doc.id, blockId);
                    urls[blockId] = r.url;
                }
                catch { /* crop not ready yet */ }
            }));
            setMarkdownFigures(urls);
            setShowMarkdown(true);
        }
        catch (err) {
            setError(`Markdown viewer: ${String(err)}`);
        }
        finally {
            setLoadingMarkdown(false);
        }
    }
    // 5. Re-ingest.
    async function handleReingest() {
        if (!confirm('Re-ingest this document? Existing chunks and index entries will be replaced.'))
            return;
        setReingesting(true);
        setError(null);
        try {
            await reingestDocument(collection.id, doc.id, true);
            const updated = await getDocument(collection.id, doc.id);
            setDoc(updated);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setReingesting(false);
        }
    }
    return (_jsxs("div", { style: { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }, children: [_jsxs("div", { className: "inspector-header", children: [_jsx("button", { type: "button", className: "btn btn-ghost", onClick: onBack, style: { flexShrink: 0 }, children: "\u2190 Back" }), _jsxs("div", { style: { flex: 1, minWidth: 0 }, children: [_jsx("div", { className: "inspector-filename", children: doc.filename }), _jsxs("div", { style: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 4, flexWrap: 'wrap' }, children: [_jsx(StatusBadge, { status: doc.status }), doc.page_count != null && _jsxs("span", { className: "text-dim", style: { fontSize: 11 }, children: [doc.page_count, " pp"] }), doc.block_count != null && _jsxs("span", { className: "text-dim", style: { fontSize: 11 }, children: [doc.block_count, " blocks"] }), doc.chunk_count != null && _jsxs("span", { className: "text-dim", style: { fontSize: 11 }, children: [doc.chunk_count, " chunks"] }), doc.language && _jsx("span", { className: "text-dim", style: { fontSize: 11 }, children: doc.language })] })] }), _jsxs("div", { className: "inspector-downloads", children: [doc.has_original && (_jsxs("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11 }, disabled: downloading === 'original', onClick: () => void handleDownload('original'), children: [downloading === 'original' ? _jsx("span", { className: "spin", children: "\u27F3" }) : '↓', " Original"] })), doc.has_pdf && (_jsxs("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11 }, disabled: downloading === 'pdf', onClick: () => void handleDownload('pdf'), children: [downloading === 'pdf' ? _jsx("span", { className: "spin", children: "\u27F3" }) : '↓', " PDF"] })), doc.has_markdown && (_jsxs(_Fragment, { children: [_jsxs("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11 }, disabled: downloading === 'markdown', onClick: () => void handleDownload('markdown'), children: [downloading === 'markdown' ? _jsx("span", { className: "spin", children: "\u27F3" }) : '↓', " IR .md"] }), _jsxs("button", { type: "button", className: `btn ${showMarkdown ? 'btn-primary' : 'btn-ghost'}`, style: { fontSize: 11 }, disabled: loadingMarkdown, onClick: () => void handleViewMarkdown(), children: [loadingMarkdown ? _jsx("span", { className: "spin", children: "\u27F3" }) : '◎', " ", showMarkdown ? 'Hide IR' : 'View IR'] })] })), _jsxs("button", { type: "button", className: "btn", style: { fontSize: 11 }, disabled: reingesting, onClick: handleReingest, children: [reingesting ? _jsx("span", { className: "spin", children: "\u27F3" }) : '↺', " Re-ingest"] })] })] }), error && (_jsx("div", { className: "error-banner", style: { margin: '8px 24px 0' }, children: error })), showMarkdown && markdownText && (_jsxs("div", { className: "markdown-viewer fadein", children: [_jsxs("div", { className: "markdown-viewer-header", children: [_jsxs("span", { children: ["IR Markdown \u2014 ", doc.filename] }), _jsx("span", { className: "text-dim", style: { fontSize: 10 }, children: Object.keys(markdownFigures).length > 0
                                    ? `${Object.keys(markdownFigures).length} figure(s) resolved`
                                    : '' }), _jsx("button", { type: "button", className: "btn-icon", onClick: () => setShowMarkdown(false), children: "\u2715" })] }), _jsx("div", { className: "markdown-content", children: _jsx(MarkdownRenderer, { text: markdownText, figureUrls: markdownFigures }) })] })), _jsx("div", { className: "inspector-scroll", children: _jsxs("div", { style: { padding: '16px 24px', maxWidth: 960, margin: '0 auto' }, children: [_jsx(S0Block, { doc: doc, collectionId: collection.id }), _jsx(S1Block, { doc: doc, collectionId: collection.id }), _jsx(StageBlock, { title: "S2 \u2014 Enrich", status: doc.status === 'done' ? 'done' : doc.status === 'error' ? 'error' : doc.status === 'running' ? 'running' : 'pending', defaultOpen: false, children: _jsx("div", { className: "text-muted", style: { fontSize: 12 }, children: "OCR / VLM enrichment results are shown inline in each FIGURE block above (kind, relevance, ocr_text, description, data_table)." }) }), _jsx(S45Block, { doc: doc, collectionId: collection.id }), _jsx(S6Block, { doc: doc, collectionId: collection.id })] }) })] }));
}
// ── Markdown renderer with inline figure images ───────────────────────────────
const FIG_LINE_RE = /^!\[fig:([^\]]+)\]\(fig:[^\)]+\)$/;
function MarkdownRenderer({ text, figureUrls }) {
    const lines = text.split('\n');
    return (_jsx(_Fragment, { children: lines.map((line, i) => {
            const m = line.match(FIG_LINE_RE);
            if (m) {
                const blockId = m[1];
                const url = figureUrls[blockId];
                return url ? (_jsxs("div", { className: "ir-figure-wrap", children: [_jsx("img", { src: url, alt: `fig:${blockId}`, className: "ir-figure-img-inline", loading: "lazy" }), _jsx("span", { className: "text-dim mono", style: { fontSize: 9, display: 'block', marginTop: 2 }, children: blockId })] }, i)) : (_jsxs("div", { className: "ir-figure-placeholder", children: ["[figure: ", blockId, "]"] }, i));
            }
            // Regular markdown line — rendered as-is in monospace
            return _jsx("div", { className: "markdown-line", children: line || ' ' }, i);
        }) }));
}
// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
    const color = status === 'done' ? 'var(--s-done)' :
        status === 'error' ? 'var(--s-error)' :
            status === 'running' ? 'var(--s-running)' :
                'var(--text-dim)';
    return (_jsxs("span", { className: "tag", style: { color, borderColor: color + '40', background: color + '10' }, children: [status === 'running' && _jsx("span", { className: "spin", style: { fontSize: 9 }, children: "\u27F3" }), status] }));
}
