import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * Renders a single input for a ParamSchema descriptor.
 * Covers: bool toggle, number (with bounds), string, secret, enum select.
 */
export function FieldInput({ schema, value, onChange, disabled }) {
    const { name, type, label, default: def, min, max, description, enum: opts } = schema;
    const displayLabel = label || name;
    const current = value ?? def;
    if (opts && opts.length > 0) {
        return (_jsxs("label", { className: "field-row", children: [_jsx("span", { className: "field-label", children: displayLabel }), _jsx("select", { className: "input select", value: String(current ?? ''), onChange: e => onChange(e.target.value), disabled: disabled, title: description, children: opts.map(o => _jsx("option", { value: o, children: o }, o)) })] }));
    }
    if (type === 'bool' || type === 'boolean') {
        return (_jsxs("label", { className: "field-row field-toggle", title: description, children: [_jsx("span", { className: "field-label", children: displayLabel }), _jsx("button", { className: `toggle ${current ? 'toggle-on' : ''}`, onClick: () => onChange(!current), disabled: disabled, type: "button", children: _jsx("span", { className: "toggle-thumb" }) })] }));
    }
    if (type === 'int' || type === 'integer' || type === 'float' || type === 'number') {
        return (_jsxs("label", { className: "field-row", title: description, children: [_jsxs("span", { className: "field-label", children: [displayLabel, (min != null || max != null) && (_jsxs("span", { className: "field-bounds", children: [min ?? '−∞', " \u2013 ", max ?? '∞'] }))] }), _jsx("input", { className: "input", type: "number", value: current ?? '', min: min ?? undefined, max: max ?? undefined, step: type === 'float' || type === 'number' ? 0.1 : 1, onChange: e => {
                        const v = type === 'float' || type === 'number'
                            ? parseFloat(e.target.value)
                            : parseInt(e.target.value, 10);
                        onChange(isNaN(v) ? undefined : v);
                    }, disabled: disabled, style: { width: 120 } })] }));
    }
    if (type === 'secret') {
        // Never pre-fill from a redacted sentinel — show empty with "already set" hint.
        const isRedacted = current === '•••';
        return (_jsxs("label", { className: "field-row", title: description, children: [_jsx("span", { className: "field-label", children: displayLabel }), _jsx("input", { className: "input mono", type: "password", placeholder: isRedacted ? '(already set — leave blank to keep)' : description || '••••••••', value: isRedacted ? '' : String(current ?? ''), onChange: e => onChange(e.target.value || undefined), disabled: disabled })] }));
    }
    // Default: string input
    return (_jsxs("label", { className: "field-row", title: description, children: [_jsx("span", { className: "field-label", children: displayLabel }), _jsx("input", { className: "input", type: "text", value: String(current ?? ''), onChange: e => onChange(e.target.value || undefined), disabled: disabled, placeholder: description })] }));
}
