import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { StageBlock } from './StageBlock';
function fmtBytes(bytes) {
    if (bytes < 1024)
        return `${bytes} B`;
    if (bytes < 1024 * 1024)
        return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
/**
 * Storage metadata block for a document.
 * Status is always "done" — if we have a Document, it was stored successfully.
 */
export function S0Block({ doc }) {
    return (_jsxs(StageBlock, { title: "S0 \u2014 Storage", summary: `${fmtBytes(doc.file_size)} · ${doc.format.toUpperCase()}`, status: "done", defaultOpen: true, children: [_jsxs("div", { className: "s0-meta-grid", children: [_jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "hash" }), _jsxs("span", { className: "s0-meta-value mono", children: [doc.source_hash.slice(0, 16), "\u2026"] })] }), _jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "format" }), _jsx("span", { className: "s0-meta-value", children: doc.format.toUpperCase() })] }), _jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "size" }), _jsx("span", { className: "s0-meta-value", children: fmtBytes(doc.file_size) })] }), _jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "created" }), _jsx("span", { className: "s0-meta-value", children: new Date(doc.created_at).toLocaleString() })] }), doc.language && (_jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "language" }), _jsx("span", { className: "s0-meta-value", children: doc.language })] })), doc.pipeline_version && (_jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: "pipeline" }), _jsx("span", { className: "s0-meta-value mono", children: doc.pipeline_version })] }))] }), Object.keys(doc.user_meta ?? {}).length > 0 && (_jsxs("div", { style: { marginTop: 12 }, children: [_jsx("div", { className: "section-title", children: "User metadata" }), _jsx("div", { className: "s0-meta-grid", children: Object.entries(doc.user_meta).map(([k, v]) => (_jsxs("div", { className: "s0-meta-item", children: [_jsx("span", { className: "s0-meta-label", children: k }), _jsx("span", { className: "s0-meta-value", children: String(v) })] }, k))) })] })), doc.pipeline_errors && doc.pipeline_errors.length > 0 && (_jsx("div", { className: "error-banner", style: { marginTop: 10 }, children: doc.pipeline_errors.map((e, i) => _jsx("div", { children: e }, i)) }))] }));
}
