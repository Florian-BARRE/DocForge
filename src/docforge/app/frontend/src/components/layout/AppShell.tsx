// ====== Code Summary ======
// AppShell — the cockpit shell layout component.
// Renders a two-region layout:
//   - Left:  NavRail (persistent collection list + global nav)
//   - Right: ContextBar (view title + collection sub-tabs + user badge) + body
//
// AUTH-B: impersonation, per-collection Access tab, and AdminView are removed.
// The "API Keys" NavRail entry (root-only) renders ApiKeysPage directly.
//
// Permission gate: `write` is derived once here from the user role and threaded
// down as a prop so DocumentsTab and PipelineTab never call useAuth() internally.

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
import { ApiKeysPage } from '../apikeys/ApiKeysPage'
import { ObservabilityDashboard } from '../observability/ObservabilityDashboard'
import { canWrite } from '../../auth/permissions'
import { useAuth } from '../../auth/AuthContext'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Cockpit shell layout — the top-level layout when a user is authenticated.
 *
 * Manages:
 *   - `activeCollectionId` — which collection is selected.
 *   - `activeView`         — which global nav zone is active.
 *   - `activeTab`          — which collection sub-tab is active.
 *   - `activeDocId`        — active document for pipeline trace mode.
 *   - `newCollectionOpen`  — SlidePanel open state for collection creation.
 *
 * Permission gate (derived once, threaded down as props):
 *   - `write` — true when the user is root; enables ingest/delete in
 *               DocumentsTab and PipelineTab.
 */
export function AppShell() {
  const { user } = useAuth()

  // 1. Collection and navigation state.
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)
  const [activeView, setActiveView]                 = useState<GlobalView>('pipeline')
  const [activeTab, setActiveTab]                   = useState<CollectionTab>('pipeline')
  const [activeDocId, setActiveDocId]               = useState<string | null>(null)
  const [newCollectionOpen, setNewCollectionOpen]   = useState(false)

  if (!user) return null

  // 2. Compute permission flag once from the current user.
  //    Root is the only authenticated role in AUTH-B.
  const write      = canWrite(user)
  const isRoot     = user.role === 'root'
  // API Keys nav entry is root-only.
  const showApiKeys = isRoot

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Selects a collection and resets document/trace state.
   * Switches to pipeline tab unless we were in apikeys/observability.
   */
  function handleSelectCollection(id: string): void {
    setActiveCollectionId(id)
    setActiveDocId(null)
    if (activeView === 'apikeys' || activeView === 'observability') {
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
   * Handles global NavRail clicks.  Syncs the sub-tab when switching to a
   * collection zone so the ContextBar highlights the correct tab.
   */
  function handleNavigate(view: GlobalView): void {
    setActiveView(view)
    // Keep sub-tab in sync for the three zones that map to collection tabs.
    if (view === 'pipeline' || view === 'documents' || view === 'search') {
      setActiveTab(view)
    }
    setActiveDocId(null)
  }

  /**
   * Handles collection sub-tab changes from the ContextBar.
   */
  function handleTabChange(tab: CollectionTab): void {
    setActiveTab(tab)
    // Sync activeView for tabs that correspond to a GlobalView entry.
    if (tab === 'pipeline' || tab === 'documents' || tab === 'search') {
      setActiveView(tab)
    }
    setActiveDocId(null)
  }

  // ── Body content ──────────────────────────────────────────────────────────

  /**
   * Resolves which zone component to render in the body region.
   *
   * Priority order:
   *   1. API Keys page (root-only global zone)
   *   2. Observability dashboard (live cockpit — monitoring bricks A/C/D)
   *   3. Empty state when no collection selected
   *   4. Collection sub-tabs: Pipeline / Documents / Search (default)
   */
  function renderBody() {
    if (activeView === 'apikeys') {
      return showApiKeys ? <ApiKeysPage /> : null
    }

    if (activeView === 'observability') {
      return <ObservabilityDashboard />
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
        showApiKeys={showApiKeys}
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
        />

        {/* Main content area */}
        <div className="app-content">
          {renderBody()}
        </div>
      </div>
    </div>
  )
}
