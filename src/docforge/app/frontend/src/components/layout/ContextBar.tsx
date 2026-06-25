// ====== Code Summary ======
// ContextBar — the horizontal top bar spanning the main content area.
// Shows: current collection name (or view name), sub-tab navigation
// (Pipeline / Documents / Search when a collection is active), user badge,
// and the theme toggle. All colors from CSS vars (token-driven).

// ====== Third-Party Library Imports ======
import { ReactNode } from 'react'

// ====== Internal Project Imports ======
import { ThemeToggle } from '../ui/ThemeToggle'
import type { GlobalView } from './NavRail'

// ── Types ────────────────────────────────────────────────────────────────────

export type CollectionTab = 'pipeline' | 'documents' | 'search'

interface ContextBarProps {
  /** Active global view (determines title + whether sub-tabs appear). */
  activeView: GlobalView
  /** Currently selected collection ID (null if none). */
  activeCollectionId: string | null
  /** Active sub-tab within a collection (only meaningful for collection views). */
  activeTab: CollectionTab
  /** Called when the user clicks a collection sub-tab. */
  onTabChange: (tab: CollectionTab) => void
  /** Authenticated username. */
  username: string
  /** Whether the user has root role. */
  isRoot: boolean
  /** Log out callback. */
  onLogout: () => void
  /** Right-side action slot (optional). */
  actions?: ReactNode
}

// ── Constants ─────────────────────────────────────────────────────────────────

const COLLECTION_TABS: { key: CollectionTab; label: string }[] = [
  { key: 'pipeline',  label: 'Pipeline'  },
  { key: 'documents', label: 'Documents' },
  { key: 'search',    label: 'Search'    },
]

const VIEW_LABEL: Record<GlobalView, string> = {
  pipeline:      'Pipeline',
  documents:     'Documents',
  search:        'Search',
  observability: 'Observability',
  admin:         'Admin',
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Horizontal context bar for the cockpit shell.
 *
 * Left side: collection name (or view title for admin/observability).
 * Center: collection sub-tabs (Pipeline / Documents / Search) — only when
 *   a collection is active and the view is not admin/observability.
 * Right side: user badge + theme toggle.
 *
 * Args:
 *   activeView: Determines what title and tabs to show.
 *   activeCollectionId: Controls whether sub-tabs are shown.
 *   activeTab: Currently selected sub-tab.
 *   onTabChange: Sub-tab selection callback.
 *   username / isRoot / onLogout: User identity and auth actions.
 *   actions: Optional extra controls injected on the right side.
 */
export function ContextBar({
  activeView,
  activeCollectionId,
  activeTab,
  onTabChange,
  username,
  isRoot,
  onLogout,
  actions,
}: ContextBarProps) {
  // 1. Determine the title to show on the left side.
  const isCollectionView = activeCollectionId !== null
    && activeView !== 'admin'
    && activeView !== 'observability'

  const title = isCollectionView
    ? activeCollectionId
    : VIEW_LABEL[activeView]

  return (
    <div className="app-header">
      {/* ── Left: view / collection title ── */}
      <span className="app-header-collection" style={{ flexShrink: 0, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
        {title ?? 'Select a collection'}
      </span>

      {/* ── Center: collection sub-tabs ── */}
      {isCollectionView && (
        <nav className="app-tabs">
          {COLLECTION_TABS.map(tab => (
            <button
              key={tab.key}
              type="button"
              className={`app-tab${activeTab === tab.key ? ' app-tab-active' : ''}`}
              onClick={() => onTabChange(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      )}

      {/* ── Right: optional actions + user badge + theme toggle ── */}
      <div className="app-header-end" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {actions}

        {/* User badge */}
        <div className="app-user-badge">
          <span className="app-user-name">{username}</span>
          {isRoot && <span className="app-user-role">root</span>}
          <button
            type="button"
            className="btn btn-ghost app-logout-btn"
            onClick={onLogout}
            title="Sign out"
          >
            Sign out
          </button>
        </div>

        <ThemeToggle />
      </div>
    </div>
  )
}
