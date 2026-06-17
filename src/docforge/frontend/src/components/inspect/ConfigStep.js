import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
// ====== Code Summary ======
// Step 2 of Inspect mode — shows and edits the pipeline config for the selected collection.
// Form fields are derived from the scoped discovery endpoint (update_config dynamic_fields).
// Mirrors the pattern established in the legacy ConfigPanel.tsx.
import { useState, useEffect } from 'react';
import { getConfigState, getConfigHistory, getDiscovery, updateConfig, rollbackConfig, } from '../../api/client';
import { ChoicePicker } from '../ui/ChoicePicker';
/**
 * Pipeline config editor driven fully by discovery dynamic_fields.
 * Groups fields by stage segment (parse, enrich, chunk, embed).
 */
export function ConfigStep({ collection, onConfigSaved }) {
    const [configState, setConfigState] = useState(null);
    const [discovery, setDiscovery] = useState(null);
    const [loading, setLoading] = useState(true);
    const [patch, setPatch] = useState({});
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState(null);
    const [history, setHistory] = useState(null);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    // 1. Load config state and scoped discovery on mount or collection change.
    useEffect(() => {
        void loadAll();
    }, [collection.id]);
    async function loadAll() {
        setLoading(true);
        setError(null);
        try {
            const [cfg, disc] = await Promise.all([
                getConfigState(collection.id),
                getDiscovery(collection.id),
            ]);
            setConfigState(cfg);
            setPatch(cfg.pipeline);
            setDiscovery(disc);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setLoading(false);
        }
    }
    // 2. Extract update_config pipeline fields from scoped discovery.
    const updateEndpoint = discovery?.endpoints.find(e => e.route_name === 'update_config');
    const pipelineFields = (updateEndpoint?.dynamic_fields ?? [])
        .filter(df => df.field_path.startsWith('patch.pipeline.'))
        .map(df => ({ ...df, field_path: df.field_path.replace('patch.pipeline.', '') }));
    // 3. Group fields by top-level stage segment.
    const stageGroups = pipelineFields.reduce((acc, df) => {
        const stage = df.field_path.split('.')[0];
        if (!acc[stage])
            acc[stage] = [];
        acc[stage].push({ ...df, field_path: df.field_path.split('.').slice(1).join('.') || df.field_path });
        return acc;
    }, {});
    const stageOrder = ['parse', 'enrich', 'chunk', 'embed'];
    const STAGE_LABELS = {
        parse: 'S1 · Parse',
        enrich: 'S2 · Enrich',
        chunk: 'S4 · Chunk',
        embed: 'S6 · Embed',
    };
    function setStageValue(stage, subPath, value) {
        setPatch(prev => {
            const stageConfig = { ...(prev[stage] ?? {}) };
            stageConfig[subPath] = value;
            return { ...prev, [stage]: stageConfig };
        });
        setSaved(false);
    }
    // 4. Save config.
    async function save() {
        setSaving(true);
        setError(null);
        try {
            const result = await updateConfig(collection.id, { pipeline: patch });
            setConfigState(result);
            setPatch(result.pipeline);
            setSaved(true);
            onConfigSaved?.(result);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setSaving(false);
        }
    }
    // 5. History helpers.
    async function loadHistory() {
        setHistoryLoading(true);
        try {
            setHistory(await getConfigHistory(collection.id));
        }
        catch { /* non-critical */ }
        finally {
            setHistoryLoading(false);
        }
    }
    function toggleHistory() {
        if (!showHistory && !history)
            void loadHistory();
        setShowHistory(v => !v);
    }
    async function handleRollback(version) {
        if (!confirm(`Roll back to version ${version}?`))
            return;
        setSaving(true);
        setError(null);
        try {
            const result = await rollbackConfig(collection.id, version);
            setConfigState(result);
            setPatch(result.pipeline);
            setSaved(true);
            await loadHistory();
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setSaving(false);
        }
    }
    if (loading) {
        return (_jsx("div", { className: "panel", children: _jsxs("div", { className: "text-muted", children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading config\u2026"] }) }));
    }
    const hasFields = pipelineFields.length > 0;
    return (_jsxs("div", { className: "panel fadein", children: [_jsxs("div", { className: "panel-header", children: [_jsx("div", { className: "panel-title", children: "Pipeline configuration" }), _jsx("div", { className: "panel-meta text-muted", children: configState && (_jsxs(_Fragment, { children: [_jsx("span", { className: "mono", children: configState.pipeline_version }), configState.needs_reindex && (_jsx("span", { className: "tag tag-running", style: { marginLeft: 8 }, children: "reindex needed" }))] })) })] }), error && _jsx("div", { className: "error-banner", children: error }), !hasFields && !loading && (_jsx("div", { className: "empty", style: { padding: '32px 0' }, children: _jsx("div", { className: "text-muted", children: discovery ? 'No configurable pipeline stages found.' : 'Discovery not available.' }) })), stageOrder.map(stage => {
                const fields = stageGroups[stage];
                if (!fields?.length)
                    return null;
                const stageConfig = (patch[stage] ?? {});
                return (_jsxs("div", { className: "config-stage-section", children: [_jsx("div", { className: "config-stage-label", children: STAGE_LABELS[stage] ?? stage }), fields.map(df => (_jsx(ChoicePicker, { field: df, value: stageConfig[df.field_path], onChange: v => setStageValue(stage, df.field_path, v) }, df.field_path)))] }, stage));
            }), hasFields && (_jsxs("div", { className: "row-end", style: { marginTop: 20 }, children: [error && _jsx("span", { style: { color: 'var(--s-error)', flex: 1, fontSize: 12 }, children: error }), saved && !error && _jsx("span", { className: "text-muted", children: "Saved." }), _jsx("button", { type: "button", className: "btn btn-ghost", onClick: () => configState && setPatch(configState.pipeline), children: "Reset" }), _jsxs("button", { type: "button", className: "btn btn-primary", onClick: save, disabled: saving, children: [saving ? _jsx("span", { className: "spin", children: "\u27F3" }) : null, saving ? ' Saving…' : 'Save config'] })] })), _jsxs("div", { className: "history-section", children: [_jsxs("button", { type: "button", className: "btn btn-ghost", style: { fontSize: 11 }, onClick: toggleHistory, children: [showHistory ? '▲' : '▼', " Config history ", history ? `(${history.total})` : ''] }), showHistory && (_jsxs("div", { className: "history-list fadein", children: [historyLoading && _jsx("div", { className: "text-muted", style: { padding: '8px 10px' }, children: "Loading\u2026" }), history?.versions.map(v => (_jsxs("div", { className: "history-row", children: [_jsxs("span", { className: "history-version mono", children: ["v", v.version] }), _jsx("span", { className: "history-pv mono text-muted", children: v.pipeline_version }), _jsx("span", { className: "history-note text-dim", children: v.note ?? '—' }), _jsx("span", { className: "history-date text-dim", children: new Date(v.created_at).toLocaleString() }), _jsx("button", { type: "button", className: "btn-icon", title: `Roll back to v${v.version}`, disabled: saving, onClick: () => void handleRollback(v.version), children: "\u21A9" })] }, v.version)))] }))] }), configState?.applied && (_jsxs("details", { className: "applied-envelope", style: { marginTop: 16 }, children: [_jsx("summary", { className: "text-muted", style: { fontSize: 11, cursor: 'pointer' }, children: "Config transparency \u25BE" }), _jsxs("div", { className: "applied-body", children: [(configState.applied.warnings?.length ?? 0) > 0 && (_jsxs("div", { children: [_jsx("span", { className: "tag tag-running", children: "warnings" }), configState.applied.warnings.map((w, i) => (_jsxs("div", { className: "applied-item text-muted", children: [w.field, ": ", w.message] }, i)))] })), (configState.applied.defaulted?.length ?? 0) > 0 && (_jsxs("div", { children: [_jsx("span", { className: "text-dim", style: { fontSize: 11 }, children: "defaulted: " }), _jsx("span", { className: "mono text-muted", style: { fontSize: 11 }, children: configState.applied.defaulted.join(', ') })] })), configState.applied.notes?.map((n, i) => (_jsx("div", { className: "applied-item text-dim", style: { fontSize: 11 }, children: n }, i)))] })] }))] }));
}
