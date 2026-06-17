import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Step 1 of Inspect mode — lists existing collections and provides a create form
// driven entirely by the discovery endpoint's dynamic_fields for create_collection.
import { useState, useEffect } from 'react';
import { listCollections, createCollection, deleteCollection, getDiscovery } from '../../api/client';
import { ChoicePicker } from '../ui/ChoicePicker';
/**
 * Discovery-driven collection listing and creation step.
 * Builds the create form from discovery dynamic_fields without hardcoding any field names.
 */
export function CollectionStep({ onSelect, selectedId }) {
    const [collections, setCollections] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [showCreate, setShowCreate] = useState(false);
    const [discovery, setDiscovery] = useState(null);
    // Create form state
    const [name, setName] = useState('');
    const [pipelineValue, setPipelineValue] = useState(undefined);
    const [creating, setCreating] = useState(false);
    const [createError, setCreateError] = useState(null);
    const [deleteId, setDeleteId] = useState(null);
    // 1. Load collections and unscoped discovery on mount.
    useEffect(() => {
        void load();
        void loadDiscovery();
    }, []);
    async function load() {
        setLoading(true);
        setError(null);
        try {
            const res = await listCollections();
            setCollections(res.collections);
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setLoading(false);
        }
    }
    async function loadDiscovery() {
        try {
            setDiscovery(await getDiscovery());
        }
        catch { /* non-critical */ }
    }
    // 2. Extract dynamic field for pipeline from the create_collection endpoint.
    const createEndpoint = discovery?.endpoints.find(e => e.route_name === 'create_collection');
    const pipelineField = createEndpoint?.dynamic_fields.find(df => df.field_path === 'pipeline');
    // 3. Submit form.
    async function handleCreate(e) {
        e.preventDefault();
        if (!name.trim())
            return;
        setCreating(true);
        setCreateError(null);
        try {
            const body = { name: name.trim() };
            if (pipelineValue !== undefined && pipelineValue !== null) {
                body.pipeline = pipelineValue;
            }
            await createCollection(body);
            setName('');
            setPipelineValue(undefined);
            setShowCreate(false);
            await load();
        }
        catch (err) {
            setCreateError(String(err));
        }
        finally {
            setCreating(false);
        }
    }
    async function handleDelete(id) {
        if (!confirm('Delete this collection and all its documents?'))
            return;
        setDeleteId(id);
        try {
            await deleteCollection(id);
            await load();
        }
        catch (err) {
            setError(String(err));
        }
        finally {
            setDeleteId(null);
        }
    }
    return (_jsxs("div", { className: "panel fadein", children: [_jsxs("div", { className: "panel-header", children: [_jsx("div", { className: "panel-title", children: "Collections" }), _jsx("button", { type: "button", className: "btn", onClick: () => setShowCreate(v => !v), children: showCreate ? '✕ Cancel' : '+ New collection' })] }), showCreate && (_jsxs("form", { className: "create-form fadein", onSubmit: handleCreate, children: [_jsxs("div", { style: { marginBottom: 12 }, children: [_jsx("div", { className: "section-title", children: "Name" }), _jsx("input", { className: "input", type: "text", placeholder: "My collection", value: name, onChange: e => setName(e.target.value), autoFocus: true })] }), pipelineField && (_jsx(ChoicePicker, { field: pipelineField, value: pipelineValue, onChange: setPipelineValue, label: "Pipeline" })), createError && _jsx("div", { className: "error-banner", children: createError }), _jsx("div", { className: "row-end", style: { marginTop: 14 }, children: _jsxs("button", { type: "submit", className: "btn btn-primary", disabled: creating || !name.trim(), children: [creating ? _jsx("span", { className: "spin", children: "\u27F3" }) : null, creating ? ' Creating…' : 'Create'] }) })] })), error && _jsx("div", { className: "error-banner", children: error }), loading ? (_jsxs("div", { className: "text-muted", style: { padding: '16px 0' }, children: [_jsx("span", { className: "spin", children: "\u27F3" }), " Loading collections\u2026"] })) : collections.length === 0 ? (_jsxs("div", { className: "empty", children: [_jsx("div", { className: "empty-icon", children: "\uD83D\uDCC1" }), _jsx("div", { children: "No collections yet. Create one to get started." })] })) : (_jsx("div", { className: "collection-list", children: collections.map(col => (_jsxs("div", { className: `collection-row ${col.id === selectedId ? 'collection-row-active' : ''}`, onClick: () => onSelect(col), children: [_jsxs("div", { className: "collection-row-main", children: [_jsx("div", { className: "collection-name", children: col.name }), _jsxs("div", { className: "text-dim", style: { fontSize: 11 }, children: [col.locality_policy, ' · ', col.embedding_model, ' · ', _jsx("span", { className: "mono", children: col.pipeline_version })] })] }), _jsx("span", { className: "tag", children: col.supported_formats.join(', ') }), _jsx("button", { type: "button", className: "btn-icon btn-icon-danger", title: "Delete collection", disabled: deleteId === col.id, onClick: e => { e.stopPropagation(); void handleDelete(col.id); }, children: deleteId === col.id ? _jsx("span", { className: "spin", children: "\u27F3" }) : '✕' })] }, col.id))) }))] }));
}
