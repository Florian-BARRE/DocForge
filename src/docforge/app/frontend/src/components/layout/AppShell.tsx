// ====== Code Summary ======
// AppShell — the cockpit shell layout component.
// Renders a three-region layout:
//   - Left:  NavRail (persistent collection list + global nav)
//   - Top:   ImpersonationBanner (when impersonating) + ContextBar
//   - Body:  the active zone/tab component
//
// Tab / view routing (UI-5 scoping):
//   - "Access" tab in ContextBar renders CollectionAccessPanel for the active
//     collection; visible only when the user is admin on that collection.
//   - "Admin" NavRail entry renders AdminView (Users + Act-as); root-only.
//   - AccountMenu in ContextBar renders ApiKeysPanel in a Drawer (every user).
//
// Permission gate: `write` and `isCollectionAdmin` are derived once here and
// threaded down as props — never re-computed inside child components.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { NavRail } from './NavRail'
import type { GlobalView } from './NavRail'
import { ContextBar } from './ContextBar'
import type { CollectionTab } from './ContextBar'
import { ImpersonationBanner } from './ImpersonationBanner'
import { SlidePanel } from './SlidePanel'
import { NewCollectionPanel } from './NewCollectionPanel'
import { PipelineTab } from '../pipeline/PipelineTab'
import { DocumentsTab } from '../documents/DocumentsTab'
import { SearchTab } from '../search/SearchTab'
import { AdminView } from '../admin/AdminView'
import { CollectionAccessPanel } from '../admin/CollectionAccessPanel'
import { ObservabilityStub } from '../observability/ObservabilityStub'
import { canWrite as computeCanWrite, canAdmin } from '../../auth/permissions'
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
 * Permission gates (derived once, threaded down as props):
 *   - `write`              — derived from canWrite(); enables ingest/delete.
 *   - `isCollectionAdmin`  — derived from canAdmin(); shows the Access tab.
 */
export function AppShell() {
  const { user, grants, isImpersonating } = useAuth()

  // 1. Collection and navigation state.
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)
  const [activeView, setActiveView]                 = useState<GlobalView>('pipeline')
  const [activeTab, setActiveTab]                   = useState<CollectionTab>('pipeline')
  const [activeDocId, setActiveDocId]               = useState<string | null>(null)
  const [newCollectionOpen, setNewCollectionOpen]   = useState(false)

  // Admin is root-only and hidden while impersonating. If impersonation starts while the
  // Admin view is active (root clicked "Act as" from there), redirect to Pipeline so the
  // impersonated session lands on a real screen (not a stale "Admin" title / empty body).
  useEffect(() => {
    if (isImpersonating && activeView === 'admin') {
      setActiveView('pipeline')
      setActiveTab('pipeline')
    }
  }, [isImpersonating, activeView])

  if (!user) return null

  // 2. Compute permission flags once from current auth state.
  const write              = computeCanWrite(user, grants, activeCollectionId)
  const isCollectionAdmin  = canAdmin(user, grants, activeCollectionId)
  // Show Admin nav entry only for the true root session — not while impersonating.
  const isRoot             = user.role === 'root'
  const showAdmin          = isRoot && !isImpersonating

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Selects a collection and resets document/trace state.
   * Switches to pipeline tab unless we were in admin/observability.
   */
  function handleSelectCollection(id: string): void {
    setActiveCollectionId(id)
    setActiveDocId(null)
    if (activeView === 'admin' || activeView === 'observability') {
      setActiveView('pipeline')
      setActiveTab('pipeline')
    }
    // The 'access' tab is admin-only and collection-specific: drop it on switch so a stale
    // selection can't carry into a collection where the user is not an admin.
    if (activeTab === 'access') setActiveTab('pipeline')
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
   * The 'access' tab does not change the global view — it stays within the
   * current collection context without affecting the NavRail selection.
   */
  function handleTabChange(tab: CollectionTab): void {
    setActiveTab(tab)
    // Only sync activeView for tabs that correspond to a GlobalView entry.
    // 'access' is collection-scoped and has no GlobalView counterpart.
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
   *   1. Admin view (root-only global zone)
   *   2. Observability stub
   *   3. Empty state when no collection selected
   *   4. Collection sub-tabs: Pipeline / Documents / Access / Search (default)
   */
  function renderBody() {
    // Admin is root-only AND hidden while impersonating; if the view is stale (e.g. root
    // clicked "Act as" from the Admin screen), fall through to the collection content so the
    // impersonated session never lands on a blank, guarded AdminView.
    if (activeView === 'admin') {
      if (showAdmin) return <AdminView />
      // fall through
    } else if (activeView === 'observability') {
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

    // Access tab — collection admin or root only. Re-checked at render (not just by hiding
    // the tab) so a stale 'access' selection after a collection switch can't show the panel
    // to a non-admin; falls through to the default tab otherwise.
    if (activeTab === 'access' && isCollectionAdmin) {
      return <CollectionAccessPanel collectionId={activeCollectionId} />
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
        showAdmin={showAdmin}
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

      {/* ── Right: impersonation banner + context bar + body ── */}
      <div className="app-main">
        {/* Impersonation warning — rendered above ContextBar for maximum visibility. */}
        <ImpersonationBanner />

        <ContextBar
          activeView={activeView}
          activeCollectionId={activeCollectionId}
          activeTab={activeTab}
          onTabChange={handleTabChange}
          username={user.username}
          isRoot={isRoot}
          isCollectionAdmin={isCollectionAdmin}
        />

        {/* Main content area */}
        <div className="app-content">
          {renderBody()}
        </div>
      </div>
    </div>
  )
}
