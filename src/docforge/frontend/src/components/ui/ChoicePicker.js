import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from 'react';
import { FieldInput } from './FieldInput';
/**
 * Renders a dynamic field: provider/method picker with conditional param inputs.
 *
 * kind="single"   → radio button group, selected option shows its params inline
 * kind="optional" → same as single but can be null (disabled)
 * kind="multi"    → ordered list builder (OCR chain etc.)
 * kind="map"      → key→value filter builder (search filters)
 * kind="weights"  → float slider per named vector
 */
export function ChoicePicker({ field, value, onChange, label }) {
    if (!field.resolved) {
        return (_jsxs("div", { className: "picker-unresolved", children: [_jsx("span", { className: "text-muted", children: label || field.field_path }), _jsx("span", { className: "tag", style: { marginLeft: 8 }, children: "collection required" })] }));
    }
    if (field.kind === 'single' || field.kind === 'optional') {
        return (_jsx(SinglePicker, { field: field, value: value, onChange: onChange, label: label }));
    }
    if (field.kind === 'multi') {
        return (_jsx(MultiPicker, { field: field, value: value, onChange: onChange, label: label }));
    }
    if (field.kind === 'map') {
        if (field.capability === 'metadata_write') {
            return (_jsx(MetadataFormPicker, { field: field, value: value, onChange: onChange, label: label }));
        }
        return (_jsx(MapPicker, { field: field, value: value, onChange: onChange, label: label }));
    }
    if (field.kind === 'weights') {
        return (_jsx(WeightsPicker, { field: field, value: value, onChange: onChange, label: label }));
    }
    return null;
}
// ── Single / optional picker ─────────────────────────────────────────────────
function SinglePicker({ field, value, onChange, label, }) {
    const defaultChoice = field.choices.find(c => c.default) ?? field.choices[0];
    const selectedId = value?.id ?? defaultChoice?.id;
    function selectChoice(c) {
        if (!c.selectable)
            return;
        const defaults = paramsDefaults(c.fields);
        onChange({ id: c.id, params: Object.keys(defaults).length ? defaults : undefined });
    }
    function updateParam(key, v) {
        const params = { ...(value?.params ?? {}), [key]: v };
        onChange({ id: selectedId, params });
    }
    const selectedChoice = field.choices.find(c => c.id === selectedId);
    return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), _jsxs("div", { className: "picker-chips", children: [field.kind === 'optional' && (_jsx("button", { className: `chip ${!selectedId ? 'chip-active' : ''}`, onClick: () => onChange(null), type: "button", children: "disabled" })), field.choices.map(c => (_jsxs("button", { className: `chip ${c.id === selectedId ? 'chip-active' : ''} ${!c.available ? 'chip-unavailable' : ''}`, onClick: () => selectChoice(c), title: c.note || (!c.available ? 'Not available in this deployment' : undefined), type: "button", disabled: !c.selectable, children: [c.label || c.id, !c.available && _jsx("span", { className: "chip-dot chip-dot-off" })] }, c.id)))] }), selectedChoice && selectedChoice.fields.length > 0 && (_jsx("div", { className: "picker-params fadein", children: selectedChoice.fields.map(p => (_jsx(FieldInput, { schema: p, value: (value?.params ?? {})[p.name], onChange: v => updateParam(p.name, v) }, p.name))) })), selectedChoice?.note && !selectedChoice.available && (_jsx("div", { className: "picker-note", children: selectedChoice.note }))] }));
}
// ── Multi / chain picker ─────────────────────────────────────────────────────
function MultiPicker({ field, value, onChange, label, }) {
    const [expanded, setExpanded] = useState(null);
    const chain = value ?? [];
    function add(c) {
        const defaults = paramsDefaults(c.fields);
        onChange([...chain, { id: c.id, params: Object.keys(defaults).length ? defaults : undefined }]);
    }
    function remove(idx) {
        onChange(chain.filter((_, i) => i !== idx));
    }
    function updateParam(idx, key, v) {
        const next = chain.map((item, i) => i === idx ? { ...item, params: { ...item.params, [key]: v } } : item);
        onChange(next);
    }
    const available = field.choices.filter(c => c.available && c.selectable);
    return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), chain.length > 0 && (_jsx("div", { className: "chain-list", children: chain.map((item, idx) => {
                    const choice = field.choices.find(c => c.id === item.id);
                    const isOpen = expanded === `${idx}`;
                    return (_jsxs("div", { className: "chain-item", children: [_jsxs("div", { className: "chain-item-row", children: [_jsx("span", { className: "chain-rank mono", children: idx + 1 }), _jsx("span", { className: "chain-id", children: choice?.label || item.id }), choice && choice.fields.length > 0 && (_jsxs("button", { className: "btn btn-ghost", style: { fontSize: 11, padding: '2px 6px' }, onClick: () => setExpanded(isOpen ? null : `${idx}`), type: "button", children: [isOpen ? '▲' : '▼', " params"] })), _jsx("button", { className: "btn btn-ghost btn-danger", onClick: () => remove(idx), type: "button", children: "\u2715" })] }), isOpen && choice && choice.fields.length > 0 && (_jsx("div", { className: "picker-params fadein", style: { marginLeft: 28 }, children: choice.fields.map(p => (_jsx(FieldInput, { schema: p, value: (item.params ?? {})[p.name], onChange: v => updateParam(idx, p.name, v) }, p.name))) }))] }, idx));
                }) })), available.length > 0 && (_jsxs("div", { className: "picker-chips", style: { marginTop: 8 }, children: [_jsx("span", { className: "text-muted", style: { fontSize: 11 }, children: "+ add" }), available.map(c => (_jsx("button", { className: "chip", onClick: () => add(c), type: "button", children: c.label || c.id }, c.id)))] })), chain.length === 0 && available.length === 0 && (_jsx("div", { className: "picker-note", children: "No providers available in this deployment." }))] }));
}
function MapPicker({ field, value, onChange, label, }) {
    const [entries, setEntries] = useState(() => {
        if (!value)
            return [];
        return Object.entries(value).map(([k, v]) => {
            const parts = k.split('::');
            return { fieldId: parts[0], op: parts[1] ?? 'eq', val: JSON.stringify(v) };
        });
    });
    function sync(next) {
        setEntries(next);
        const built = {};
        next.forEach(e => {
            if (e.fieldId && e.val) {
                const key = `${e.fieldId}::${e.op}`;
                try {
                    built[key] = JSON.parse(e.val);
                }
                catch {
                    built[key] = e.val;
                }
            }
        });
        onChange(built);
    }
    function addEntry() {
        sync([...entries, { fieldId: '', op: 'eq', val: '' }]);
    }
    function updateEntry(idx, patch) {
        sync(entries.map((e, i) => i === idx ? { ...e, ...patch } : e));
    }
    function removeEntry(idx) {
        sync(entries.filter((_, i) => i !== idx));
    }
    const fieldIds = field.choices.map(c => c.id);
    return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), entries.map((entry, idx) => {
                const choice = field.choices.find(c => c.id === entry.fieldId);
                const opField = choice?.fields.find(f => f.name === 'op');
                const ops = opField?.enum ?? ['eq'];
                return (_jsxs("div", { className: "filter-row", children: [_jsxs("select", { className: "input select", value: entry.fieldId, onChange: e => updateEntry(idx, { fieldId: e.target.value, op: 'eq' }), style: { width: 140 }, children: [_jsx("option", { value: "", children: "\u2014 field \u2014" }), fieldIds.map(id => _jsx("option", { value: id, children: id }, id))] }), _jsx("select", { className: "input select", value: entry.op, onChange: e => updateEntry(idx, { op: e.target.value }), style: { width: 80 }, children: ops.map(op => _jsx("option", { value: op, children: op }, op)) }), _jsx("input", { className: "input", value: entry.val, onChange: e => updateEntry(idx, { val: e.target.value }), placeholder: 'value or ["a","b"]', style: { flex: 1 } }), _jsx("button", { className: "btn btn-ghost btn-danger", onClick: () => removeEntry(idx), type: "button", children: "\u2715" })] }, idx));
            }), _jsx("button", { className: "btn", style: { marginTop: 6, fontSize: 12 }, onClick: addEntry, type: "button", children: "+ add filter" })] }));
}
// ── Weights picker ────────────────────────────────────────────────────────────
function WeightsPicker({ field, value, onChange, label, }) {
    const current = value ?? {};
    function update(id, v) {
        onChange({ ...current, [id]: v });
    }
    return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), field.choices.map(c => {
                const w = current[c.id] ?? (c.fields[0]?.default ?? 1.0);
                return (_jsxs("div", { className: "weight-row", children: [_jsx("span", { className: "weight-id mono", children: c.id }), _jsx("input", { type: "range", min: 0, max: 2, step: 0.05, value: w, onChange: e => update(c.id, parseFloat(e.target.value)), className: "weight-slider" }), _jsx("span", { className: "weight-val mono", children: w.toFixed(2) })] }, c.id));
            })] }));
}
// ── Metadata form picker (kind=map + capability=metadata_write) ───────────────
// One typed input per custom field, with type badge and required/optional indicator.
// Produces { field_name: value } (no operator — raw metadata object for ingest).
function MetadataFormPicker({ field, value, onChange, label, }) {
    const current = value ?? {};
    function set(fieldId, v) {
        const next = { ...current };
        if (v === undefined || v === '' || v === null) {
            delete next[fieldId];
        }
        else {
            next[fieldId] = v;
        }
        onChange(next);
    }
    if (field.choices.length === 0) {
        return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), _jsx("div", { className: "picker-unresolved text-muted", style: { fontSize: 12 }, children: "No custom metadata fields defined on this collection." })] }));
    }
    return (_jsxs("div", { className: "picker", children: [_jsx("div", { className: "picker-label", children: label || labelFromPath(field.field_path) }), _jsx("div", { className: "meta-form", children: field.choices.map(c => {
                    const valueSchema = c.fields[0];
                    const isRequired = c.note === 'required';
                    return (_jsxs("div", { className: "meta-form-row", children: [_jsxs("div", { className: "meta-form-label", children: [_jsx("span", { className: "meta-field-name mono", children: c.label || c.id }), _jsx("span", { className: `tag ${isRequired ? 'tag-running' : ''}`, style: { fontSize: 10 }, children: isRequired ? 'required' : 'optional' }), valueSchema && (_jsx("span", { className: "tag", style: { fontSize: 10, marginLeft: 4 }, children: valueSchema.type }))] }), valueSchema ? (_jsx(MetaFieldInput, { schema: valueSchema, value: current[c.id], onChange: v => set(c.id, v), required: isRequired })) : (_jsx("input", { className: "input", type: "text", value: String(current[c.id] ?? ''), onChange: e => set(c.id, e.target.value || undefined), placeholder: c.id }))] }, c.id));
                }) })] }));
}
// Thin wrapper around FieldInput that handles enum → select and bool → toggle inline.
function MetaFieldInput({ schema, value, onChange, required, }) {
    // Enum field — native select with empty first option if optional
    if (schema.enum && schema.enum.length > 0) {
        return (_jsxs("select", { className: "input select", value: String(value ?? ''), onChange: e => onChange(e.target.value || undefined), style: { flex: 1 }, children: [!required && _jsx("option", { value: "", children: "\u2014" }), schema.enum.map(o => _jsx("option", { value: o, children: o }, o))] }));
    }
    // Bool field
    if (schema.type === 'bool' || schema.type === 'boolean') {
        const checked = Boolean(value ?? false);
        return (_jsx("button", { className: `toggle ${checked ? 'toggle-on' : ''}`, onClick: () => onChange(!checked), type: "button", style: { flex: 'none' }, children: _jsx("span", { className: "toggle-thumb" }) }));
    }
    // Number field
    if (schema.type === 'int' || schema.type === 'integer' || schema.type === 'float' || schema.type === 'number') {
        return (_jsx("input", { className: "input", type: "number", value: value !== undefined && value !== null ? String(value) : '', min: schema.min ?? undefined, max: schema.max ?? undefined, step: schema.type === 'float' || schema.type === 'number' ? 0.1 : 1, onChange: e => {
                const n = schema.type === 'float' || schema.type === 'number'
                    ? parseFloat(e.target.value)
                    : parseInt(e.target.value, 10);
                onChange(isNaN(n) ? undefined : n);
            }, placeholder: required ? schema.name : `${schema.name} (optional)`, style: { flex: 1 } }));
    }
    // Default: string
    return (_jsx("input", { className: "input", type: "text", value: String(value ?? ''), onChange: e => onChange(e.target.value || undefined), placeholder: required ? schema.name : `${schema.name} (optional)`, style: { flex: 1 } }));
}
// ── Utilities ─────────────────────────────────────────────────────────────────
function paramsDefaults(fields) {
    const out = {};
    fields.forEach(f => { if (f.default !== undefined && f.default !== null)
        out[f.name] = f.default; });
    return out;
}
function labelFromPath(path) {
    const last = path.split('.').pop() ?? path;
    return last.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}
