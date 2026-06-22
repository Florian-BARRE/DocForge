// ====== Code Summary ======
// Root application component — new shell layout with a persistent collection
// sidebar on the left, a per-collection header with three sub-tabs (Pipeline,
// Documents, Search), and a main content area.  The old view components
// (InspectView, BrowseView, SearchView) are no longer rendered from this root;
// each tab will mount its own dedicated component in subsequent tasks.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { CollectionSidebar } from './components/layout/CollectionSidebar'
import { DocumentsTab } from './components/documents/DocumentsTab'
import { PipelineTab } from './components/pipeline/PipelineTab'
import { SearchTab } from './components/search/SearchTab'
import { ThemeToggle } from './components/ui/ThemeToggle'
import './global.css'

// ── Types ────────────────────────────────────────────────────────────────────

type AppTab = 'pipeline' | 'documents' | 'search'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Root application component for DocForge.
 *
 * Renders a two-column shell:
 *   - Left: {@link CollectionSidebar} — fixed-width sidebar that lists all
 *     collections and owns its own polling loop.
 *   - Right: a flex-column area containing a sticky header (collection name +
 *     three sub-tabs + theme toggle) and the active tab's content.
 *
 * State managed here:
 *   - `activeCollectionId` — which collection is selected (null = nothing selected).
 *   - `activeTab`          — which of the three sub-tabs is active.
 *   - `activeDocId`        — document selected inside a tab (for trace/detail mode).
 *     Declared here so it can be passed down to tab components in later tasks.
 *
 * The theme is fully managed by {@link ThemeToggle} (reads/writes localStorage
 * and sets `data-theme` on `<html>`).  No theme state is hoisted here.
 */
export function App() {
  // 1. Collection selection — null means "no collection chosen yet".
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)

  // 2. Active sub-tab within the selected collection.
  const [activeTab, setActiveTab] = useState<AppTab>('pipeline')

  // 3. Active document ID — used by PipelineTab for trace mode (T5) and will be
  //    passed to DocumentsTab once that component is wired in T6.
  const [activeDocId, setActiveDocId] = useState<string | null>(null)

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Selects a collection and resets the active document so the new tab renders
   * from a clean state.
   *
   * Args:
   *   id: The ID of the collection that was clicked in the sidebar.
   */
  function handleSelectCollection(id: string): void {
    setActiveCollectionId(id)
    setActiveDocId(null)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="app-shell">
      {/* ── Left: collection sidebar ── */}
      <CollectionSidebar
        activeCollectionId={activeCollectionId}
        onSelect={handleSelectCollection}
        onNew={() => {
          // Placeholder — will open a "New Collection" modal in a future task.
        }}
      />

      {/* ── Right: header + content ── */}
      <div className="app-main">
        {/* Header bar: collection name, tab nav, theme toggle */}
        <div className="app-header">
          <span className="app-header-collection">
            {activeCollectionId ?? 'No collection selected'}
          </span>

          {/* Sub-tab navigation — only shown when a collection is selected */}
          {activeCollectionId && (
            <nav className="app-tabs">
              {(['pipeline', 'documents', 'search'] as const).map(tab => (
                <button
                  key={tab}
                  type="button"
                  className={`app-tab${activeTab === tab ? ' app-tab-active' : ''}`}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab.charAt(0).toUpperCase() + tab.slice(1)}
                </button>
              ))}
            </nav>
          )}

          {/* Theme toggle — pushed to the right end of the header */}
          <div className="app-header-end">
            <ThemeToggle />
          </div>
        </div>

        {/* Main content area — renders the active tab or an empty state */}
        <div className="app-content">
          {!activeCollectionId ? (
            /* Empty state: no collection selected */
            <div className="app-empty">
              <span>Select a collection to begin</span>
            </div>
          ) : activeTab === 'pipeline' ? (
            <PipelineTab
              collectionId={activeCollectionId}
              activeDocId={activeDocId}
              onRequestTrace={(docId) => setActiveDocId(docId)}
            />
          ) : activeTab === 'documents' ? (
            <DocumentsTab
              collectionId={activeCollectionId}
              onTrace={(docId) => {
                // Select the document and jump to the Pipeline tab in trace mode.
                setActiveDocId(docId)
                setActiveTab('pipeline')
              }}
            />
          ) : (
            <SearchTab collectionId={activeCollectionId} />
          )}
        </div>
      </div>
    </div>
  )
}

export default App
