// ====== Code Summary ======
// AdminView — the top-level admin area, gated to root users.
// Contains three tabs: Users (root only), API Keys (any user), and
// Collaborators (root or collection admin).

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import { useAuth } from '../../auth/AuthContext'
import { canAdmin } from '../../auth/permissions'
import { ApiKeysPanel } from './ApiKeysPanel'
import { UsersPanel } from './UsersPanel'
import { CollectionAccessPanel } from './CollectionAccessPanel'

// ── Types ────────────────────────────────────────────────────────────────────

interface AdminViewProps {
  /** Currently selected collection, for the Collaborators panel. */
  activeCollectionId: string | null
}

type AdminTab = 'api-keys' | 'users' | 'collaborators'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Admin area rendered when the user clicks "Admin" in the app header.
 *
 * Tab visibility rules:
 *   - "API Keys": always visible (any authenticated user).
 *   - "Users":    only visible to root.
 *   - "Collaborators": only visible when a collection is selected and the
 *       current user is a collection admin or root.
 *
 * Args:
 *   activeCollectionId: The collection currently selected in the sidebar,
 *     used to scope the Collaborators panel.
 */
export function AdminView({ activeCollectionId }: AdminViewProps) {
  const { user, grants } = useAuth()
  const [activeTab, setActiveTab] = useState<AdminTab>('api-keys')

  if (!user) return null

  const isRoot = user.role === 'root'
  const isCollectionAdmin = activeCollectionId
    ? canAdmin(user, grants, activeCollectionId)
    : false
  const showCollaborators = isRoot || isCollectionAdmin

  return (
    <div className="admin-view">
      {/* Tab bar */}
      <div className="admin-tabs">
        <button
          type="button"
          className={`app-tab${activeTab === 'api-keys' ? ' app-tab-active' : ''}`}
          onClick={() => setActiveTab('api-keys')}
        >
          API Keys
        </button>
        {isRoot && (
          <button
            type="button"
            className={`app-tab${activeTab === 'users' ? ' app-tab-active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            Users
          </button>
        )}
        {showCollaborators && (
          <button
            type="button"
            className={`app-tab${activeTab === 'collaborators' ? ' app-tab-active' : ''}`}
            onClick={() => setActiveTab('collaborators')}
          >
            Collaborators
          </button>
        )}
      </div>

      {/* Tab content */}
      <div className="admin-content">
        {activeTab === 'api-keys' && <ApiKeysPanel />}
        {activeTab === 'users' && isRoot && <UsersPanel />}
        {activeTab === 'collaborators' && showCollaborators && (
          activeCollectionId ? (
            <CollectionAccessPanel collectionId={activeCollectionId} />
          ) : (
            <div className="admin-section">
              <p className="text-muted" style={{ fontSize: 13 }}>
                Select a collection in the sidebar to manage its collaborators.
              </p>
            </div>
          )
        )}
      </div>
    </div>
  )
}
