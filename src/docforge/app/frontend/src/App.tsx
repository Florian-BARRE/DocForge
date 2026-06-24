// ====== Code Summary ======
// Root application component — new shell layout with a persistent collection
// sidebar on the left, a per-collection header with three sub-tabs (Pipeline,
// Documents, Search), and a main content area.  The old view components
// (InspectView, BrowseView, SearchView) are no longer rendered from this root;
// each tab will mount its own dedicated component in subsequent tasks.
//
// Auth gate: renders <LoginScreen> when no authenticated session is present;
// renders the normal shell once the user is logged in.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { CollectionSidebar } from './components/layout/CollectionSidebar'
import { NewCollectionPanel } from './components/layout/NewCollectionPanel'
import { SlidePanel } from './components/layout/SlidePanel'
import { DocumentsTab } from './components/documents/DocumentsTab'
import { PipelineTab } from './components/pipeline/PipelineTab'
import { SearchTab } from './components/search/SearchTab'
import { ThemeToggle } from './components/ui/ThemeToggle'
import { AdminView } from './components/admin/AdminView'
import { useAuth } from './auth/AuthContext'
import { LoginScreen } from './auth/LoginScreen'
import { canWrite as computeCanWrite } from './auth/permissions'
import './global.css'

// ── Types ────────────────────────────────────────────────────────────────────

type AppTab = 'pipeline' | 'documents' | 'search' | 'admin'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Root application component for DocForge.
 *
 * Renders a two-column shell:
 *   - Left: {@link CollectionSidebar} — fixed-width sidebar that lists all
 *     collections and owns its own polling loop.
 *   - Right: a flex-column area containing a sticky header (collection name +
 *     three sub-tabs + theme toggle + user info) and the active tab's content.
 *
 * State managed here:
 *   - `activeCollectionId` — which collection is selected (null = nothing selected).
 *   - `activeTab`          — which of the three sub-tabs is active.
 *   - `activeDocId`        — document selected inside a tab (for trace/detail mode).
 *
 * Auth gate: shows {@link LoginScreen} when `user` is null (no session), and the
 * normal shell once authenticated.  The `loading` flag prevents a flash of the
 * login screen while the stored token is being rehydrated on mount.
 *
 * The theme is fully managed by {@link ThemeToggle} (reads/writes localStorage
 * and sets `data-theme` on `<html>`).  No theme state is hoisted here.
 */
export function App() {
  const { user, grants, logout, loading } = useAuth()

  // 1. Collection selection — null means "no collection chosen yet".
  const [activeCollectionId, setActiveCollectionId] = useState<string | null>(null)

  // 2. Active sub-tab within the selected collection.
  const [activeTab, setActiveTab] = useState<AppTab>('pipeline')

  // 3. Active document ID — used by PipelineTab for trace mode.
  const [activeDocId, setActiveDocId] = useState<string | null>(null)

  // 4. New collection SlidePanel open state.
  const [newCollectionOpen, setNewCollectionOpen] = useState(false)

  // ── Auth gate ─────────────────────────────────────────────────────────────

  // While the stored token is being validated on mount, render nothing to avoid
  // a login-screen flash for users who are already authenticated.
  if (loading) {
    return (
      <div className="app-loading">
        <span className="app-loading-text">Loading...</span>
      </div>
    )
  }

  // No authenticated user — show the login screen.
  if (!user) return <LoginScreen />

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
    // Stay on the current tab unless we were in admin.
    if (activeTab === 'admin') setActiveTab('pipeline')
  }

  /**
   * Called after successful collection creation.
   * Selects the new collection and jumps straight to the Pipeline tab so
   * the user can configure it via the discovery-driven graph.
   *
   * Args:
   *   id: The newly created collection's ID.
   */
  function handleCollectionCreated(id: string): void {
    setNewCollectionOpen(false)
    setActiveCollectionId(id)
    setActiveDocId(null)
    setActiveTab('pipeline')
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const isRoot = user.role === 'root'

  // Permission flag derived from the current user's grant on the active collection.
  // Root users always receive the highest level of access (canWrite returns true for root).
  const write = computeCanWrite(user, grants, activeCollectionId)

  return (
    <div className="app-shell">
      {/* ── Left: collection sidebar ── */}
      <CollectionSidebar
        activeCollectionId={activeCollectionId}
        onSelect={handleSelectCollection}
        onNew={() => setNewCollectionOpen(true)}
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

      {/* ── Right: header + content ── */}
      <div className="app-main">
        {/* Header bar: collection name, tab nav, user info, theme toggle */}
        <div className="app-header">
          <span className="app-header-collection">
            {activeTab === 'admin'
              ? 'Admin'
              : (activeCollectionId ?? 'No collection selected')}
          </span>

          {/* Sub-tab navigation — only shown when a collection is selected (not in admin) */}
          {activeCollectionId && activeTab !== 'admin' && (
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

          {/* Right-side: admin link (root only) + user badge + theme toggle */}
          <div className="app-header-end">
            {isRoot && (
              <button
                type="button"
                className={`btn btn-ghost app-header-admin${activeTab === 'admin' ? ' app-tab-active' : ''}`}
                onClick={() => setActiveTab('admin')}
                title="Admin panel"
              >
                Admin
              </button>
            )}

            {/* User badge — shows username and a logout button */}
            <div className="app-user-badge">
              <span className="app-user-name">{user.username}</span>
              {user.role === 'root' && (
                <span className="app-user-role">root</span>
              )}
              <button
                type="button"
                className="btn btn-ghost app-logout-btn"
                onClick={logout}
                title="Sign out"
              >
                Sign out
              </button>
            </div>

            <ThemeToggle />
          </div>
        </div>

        {/* Main content area — renders the active tab or an empty state */}
        <div className="app-content">
          {activeTab === 'admin' ? (
            <AdminView activeCollectionId={activeCollectionId} />
          ) : !activeCollectionId ? (
            /* Empty state: no collection selected */
            <div className="app-empty">
              <span>Select a collection to begin</span>
            </div>
          ) : activeTab === 'pipeline' ? (
            <PipelineTab
              collectionId={activeCollectionId}
              activeDocId={activeDocId}
              onRequestTrace={(docId) => setActiveDocId(docId)}
              canWrite={write}
            />
          ) : activeTab === 'documents' ? (
            <DocumentsTab
              collectionId={activeCollectionId}
              onTrace={(docId) => {
                // Select the document and jump to the Pipeline tab in trace mode.
                setActiveDocId(docId)
                setActiveTab('pipeline')
              }}
              canWrite={write}
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
