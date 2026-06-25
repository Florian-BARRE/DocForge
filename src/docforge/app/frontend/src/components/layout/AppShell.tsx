// ====== Code Summary ======
// AppShell — the cockpit shell layout component.
// Renders a three-region layout:
//   - Left: NavRail (persistent collection list + global nav)
//   - Top:  ContextBar (collection title + sub-tabs + user + theme toggle)
//   - Body: the active zone/tab component
// Existing screen components (PipelineTab, DocumentsTab, SearchTab, AdminView)
// are mounted unchanged inside the body region — their internals are untouched.
// A right-side panel slot is provided for future inspector panels.

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { NavRail } from './NavRail'
import type { GlobalView } from './NavRail'
import { ContextBar } from './ContextBar'
import type { CollectionTab } from './ContextBar'
import { SlidePanel } from './SlidePanel'
import { NewCollectionPanel } from './NewCollectionPanel'
import { PipelineTab } from '../pipeline/PipelineTab'
import { DocumentsTab } from '../documents/DocumentsTab'
import { SearchTab } from '../search/SearchTab'
import { AdminView } from '../admin/AdminView'
import { ObservabilityStub } from '../observability/ObservabilityStub'
import { canWrite as computeCanWrite } from '../../auth/permissions'
import { useAuth } from '../../auth/AuthContext'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Cockpit shell layout — the top-level layout when a user is authenticated.
 *
 * Manages:
 *   - `activeCollectionId` — which collection is selected.
 *   - `activeView` — which global nav zone is active.
 *   - `activeTab` — which collection sub-tab is active.
 *   - `activeDocId` — active document for pipeline trace mode.
 *   - `newCollectionOpen` — SlidePanel open state for collection creation.
 *
 * Permission gate: `write` is derived once from `canWrite()` and threaded
 * down as a prop — never called inside child components.
 */
export function AppShell() {
  const { user, grants, logout } = useAuth()

  // 1. Collection and navigation state.
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)
  const [activeView, setActiveView]                 = useState<GlobalView>('pipeline')
  const [activeTab, setActiveTab]                   = useState<CollectionTab>('pipeline')
  const [activeDocId, setActiveDocId]               = useState<string | null>(null)
  const [newCollectionOpen, setNewCollectionOpen]   = useState(false)

  if (!user) return null

  // 2. Compute write permission once from current auth state.
  const write  = computeCanWrite(user, grants, activeCollectionId)
  const isRoot = user.role === 'root'

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Selects a collection and resets document/trace state.
   * Switches to the current activeTab unless we were in admin/observability.
   */
  function handleSelectCollection(id: string): void {
    setActiveCollectionId(id)
    setActiveDocId(null)
    if (activeView === 'admin' || activeView === 'observability') {
      setActiveView('pipeline')
      setActiveTab('pipeline')
    }
  }

  /**
   * Called after successful collection creation.
   * Selects the new collection and jumps to Pipeline tab.
   */
  function handleCollectionCreated(id: string): void {
    setNewCollectionOpen(false)
    setActiveCollectionId(id)
    setActiveDocId(null)
    setActiveView('pipeline')
    setActiveTab('pipeline')
  }

  /**
   * Handles global nav rail clicks. When switching to a collection zone,
   * syncs the sub-tab so the context bar reflects the right active tab.
   */
  function handleNavigate(view: GlobalView): void {
    setActiveView(view)
    // If the view corresponds to a collection sub-tab, sync the tab state.
    if (view === 'pipeline' || view === 'documents' || view === 'search') {
      setActiveTab(view)
    }
    setActiveDocId(null)
  }

  /**
   * Handles collection sub-tab changes from the ContextBar.
   * Keeps activeView in sync with the selected tab.
   */
  function handleTabChange(tab: CollectionTab): void {
    setActiveTab(tab)
    setActiveView(tab)
    setActiveDocId(null)
  }

  // ── Body content ──────────────────────────────────────────────────────────

  /**
   * Resolves which zone component to render in the body region.
   */
  function renderBody() {
    if (activeView === 'admin') {
      return <AdminView activeCollectionId={activeCollectionId} />
    }

    if (activeView === 'observability') {
      return <ObservabilityStub />
    }

    // Collection zone — requires a collection to be selected.
    if (!activeCollectionId) {
      return (
        <div className="app-empty">
          <span>Select a collection to begin</span>
        </div>
      )
    }

    if (activeTab === 'pipeline') {
      return (
        <PipelineTab
          collectionId={activeCollectionId}
          activeDocId={activeDocId}
          onRequestTrace={docId => setActiveDocId(docId)}
          canWrite={write}
        />
      )
    }

    if (activeTab === 'documents') {
      return (
        <DocumentsTab
          collectionId={activeCollectionId}
          onTrace={docId => {
            setActiveDocId(docId)
            setActiveTab('pipeline')
            setActiveView('pipeline')
          }}
          canWrite={write}
        />
      )
    }

    return <SearchTab collectionId={activeCollectionId} />
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="app-shell">
      {/* ── Left: persistent nav rail ── */}
      <NavRail
        activeView={activeView}
        activeCollectionId={activeCollectionId}
        onSelectCollection={handleSelectCollection}
        onNew={() => setNewCollectionOpen(true)}
        onNavigate={handleNavigate}
        showAdmin={isRoot}
      />

      {/* ── New collection slide panel ── */}
      <SlidePanel
        isOpen={newCollectionOpen}
        title="New Collection"
        onClose={() => setNewCollectionOpen(false)}
      >
        <NewCollectionPanel
          onCreated={handleCollectionCreated}
          onCancel={() => setNewCollectionOpen(false)}
        />
      </SlidePanel>

      {/* ── Right: context bar + body ── */}
      <div className="app-main">
        <ContextBar
          activeView={activeView}
          activeCollectionId={activeCollectionId}
          activeTab={activeTab}
          onTabChange={handleTabChange}
          username={user.username}
          isRoot={isRoot}
          onLogout={logout}
        />

        {/* Main content area */}
        <div className="app-content">
          {renderBody()}
        </div>
      </div>
    </div>
  )
}
