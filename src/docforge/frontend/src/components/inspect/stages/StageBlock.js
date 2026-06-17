import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Generic collapsible stage block used as shell for all pipeline stages.
// Handles expand/collapse, status badge rendering, and spinner for running state.
import { useState } from 'react';
const STATUS_COLORS = {
    done: 'var(--s-done)',
    running: 'var(--s-running)',
    error: 'var(--s-error)',
    pending: 'var(--text-dim)',
};
const STATUS_LABELS = {
    done: 'done',
    running: 'running',
    error: 'error',
    pending: 'pending',
};
/**
 * Maps a DocStatus to a StageStatus for per-stage display.
 */
export function docStatusToStage(status) {
    if (status === 'done')
        return 'done';
    if (status === 'error')
        return 'error';
    if (status === 'running')
        return 'running';
    return 'pending';
}
/**
 * Collapsible block for a pipeline stage.
 * Renders a header row with title, summary, and status badge.
 */
export function StageBlock({ title, summary, status, defaultOpen = false, children }) {
    const [open, setOpen] = useState(defaultOpen);
    const blockClass = [
        'stage-block',
        status === 'done' ? 'stage-block-done' : '',
        status === 'error' ? 'stage-block-error' : '',
        status === 'running' ? 'stage-block-running' : '',
    ].filter(Boolean).join(' ');
    return (_jsxs("div", { className: blockClass, children: [_jsxs("div", { className: "stage-header", onClick: () => setOpen(v => !v), children: [status === 'running' && (_jsx("span", { className: "spin", style: { fontSize: 12, color: 'var(--s-running)' }, children: "\u27F3" })), _jsx("span", { className: "stage-title", children: title }), summary && (_jsx("span", { className: "stage-summary", children: summary })), _jsx("span", { className: "tag", style: {
                            color: STATUS_COLORS[status],
                            borderColor: STATUS_COLORS[status] + '40',
                            background: STATUS_COLORS[status] + '10',
                            flexShrink: 0,
                        }, children: STATUS_LABELS[status] }), _jsx("span", { className: "stage-chevron", children: open ? '▲' : '▼' })] }), open && children && (_jsx("div", { className: "stage-body fadein", children: children }))] }));
}
