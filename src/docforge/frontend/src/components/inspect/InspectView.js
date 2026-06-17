import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Inspect mode — 4-step rail: Collection → Config → Ingest → Inspector.
// Each step is a separate component. State flows downward via props.
import { useState, useEffect } from 'react';
import { CollectionStep } from './CollectionStep';
import { ConfigStep } from './ConfigStep';
import { IngestStep } from './IngestStep';
import { PipelineInspector } from './PipelineInspector';
function StepNode({ step, label, current, done, onClick }) {
    const isActive = step === current;
    const classes = [
        'step-node',
        isActive ? 'step-node-active' : '',
        done && !isActive ? 'step-node-done' : '',
    ].filter(Boolean).join(' ');
    return (_jsxs("button", { type: "button", className: classes, onClick: onClick, children: [_jsx("span", { className: "step-number", children: done && !isActive ? _jsx("span", { className: "step-check", children: "\u2713" }) : step }), label] }));
}
/**
 * 4-step Inspect view. Manages which step is active and passes state downward.
 * Preloaded collection/doc from BrowseView "Inspect" is applied on mount.
 */
export function InspectView({ preloadedCollection, preloadedDoc, onTargetConsumed }) {
    const [step, setStep] = useState(1);
    const [collection, setCollection] = useState(null);
    const [inspectDoc, setInspectDoc] = useState(null);
    // Apply preloaded target when it arrives (from BrowseView "Inspect" button).
    useEffect(() => {
        if (preloadedCollection && preloadedDoc) {
            setCollection(preloadedCollection);
            setInspectDoc(preloadedDoc);
            setStep(4);
            onTargetConsumed();
        }
    }, [preloadedCollection, preloadedDoc]);
    function selectCollection(col) {
        setCollection(col);
        setStep(2);
    }
    function handleIngested(doc) {
        setInspectDoc(doc);
        setStep(4);
    }
    function canNavigateTo(s) {
        if (s === 1)
            return true;
        if (s === 2)
            return collection !== null;
        if (s === 3)
            return collection !== null;
        if (s === 4)
            return collection !== null && inspectDoc !== null;
        return false;
    }
    function navigate(s) {
        if (canNavigateTo(s))
            setStep(s);
    }
    return (_jsxs("div", { style: { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }, children: [_jsx("div", { className: "step-rail-wrapper", children: _jsxs("div", { className: "step-rail", children: [_jsx(StepNode, { step: 1, label: collection ? `Collection: ${collection.name}` : 'Collection', current: step, done: collection !== null, onClick: () => navigate(1) }), _jsx("span", { className: "step-arrow", children: "\u2192" }), _jsx(StepNode, { step: 2, label: "Config", current: step, done: step > 2 && collection !== null, onClick: () => navigate(2) }), _jsx("span", { className: "step-arrow", children: "\u2192" }), _jsx(StepNode, { step: 3, label: "Ingest", current: step, done: step > 3 && inspectDoc !== null, onClick: () => navigate(3) }), _jsx("span", { className: "step-arrow", children: "\u2192" }), _jsx(StepNode, { step: 4, label: inspectDoc ? `Inspector: ${inspectDoc.filename}` : 'Inspector', current: step, done: false, onClick: () => navigate(4) })] }) }), _jsxs("div", { className: "inspect-scroll", children: [step === 1 && (_jsx(CollectionStep, { onSelect: selectCollection, selectedId: collection?.id ?? null })), step === 2 && collection && (_jsx(ConfigStep, { collection: collection })), step === 3 && collection && (_jsx(IngestStep, { collection: collection, onIngested: handleIngested })), step === 4 && collection && inspectDoc && (_jsx(PipelineInspector, { collection: collection, initialDoc: inspectDoc, onBack: () => setStep(3) })), step === 2 && !collection && (_jsx("div", { className: "empty", children: _jsx("div", { className: "text-dim", children: "Select a collection first." }) })), step === 4 && (!collection || !inspectDoc) && (_jsx("div", { className: "empty", children: _jsx("div", { className: "text-dim", children: "Ingest a document first." }) }))] })] }));
}
