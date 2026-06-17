import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
// ====== Code Summary ======
// Root application component — tab navigation between Inspect, Browse, and Search views.
// No global context; each view manages its own state. Tab switching is orchestrated here.
import { useState } from 'react';
import { InspectView } from './components/inspect/InspectView';
import { BrowseView } from './components/browse/BrowseView';
import { SearchView } from './components/search/SearchView';
import './global.css';
export function App() {
    const [tab, setTab] = useState('inspect');
    const [inspectTarget, setInspectTarget] = useState(null);
    // Called by BrowseView when user clicks "Inspect" on a document.
    function handleInspect(collection, doc) {
        setInspectTarget({ collection, doc });
        setTab('inspect');
    }
    function switchTab(t) {
        setTab(t);
    }
    return (_jsxs("div", { className: "shell", children: [_jsxs("header", { className: "topbar", children: [_jsx("span", { className: "topbar-logo", children: "DocForge" }), _jsxs("nav", { className: "topbar-tabs", children: [_jsx("button", { type: "button", className: `topbar-tab ${tab === 'inspect' ? 'topbar-tab-active' : ''}`, onClick: () => switchTab('inspect'), children: "Inspect" }), _jsx("button", { type: "button", className: `topbar-tab ${tab === 'browse' ? 'topbar-tab-active' : ''}`, onClick: () => switchTab('browse'), children: "Collections" }), _jsx("button", { type: "button", className: `topbar-tab ${tab === 'search' ? 'topbar-tab-active' : ''}`, onClick: () => switchTab('search'), children: "Search" })] })] }), _jsxs("div", { className: "main-content", children: [tab === 'inspect' && (_jsx(InspectView, { preloadedCollection: inspectTarget?.collection ?? null, preloadedDoc: inspectTarget?.doc ?? null, onTargetConsumed: () => setInspectTarget(null) })), tab === 'browse' && (_jsx(BrowseView, { onInspect: handleInspect })), tab === 'search' && (_jsx(SearchView, {}))] })] }));
}
export default App;
