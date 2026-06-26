// ====== Code Summary ======
// ContextBar — the horizontal top bar spanning the main content area.
// Shows: current collection name (or view name), sub-tab navigation
// (Pipeline / Documents / Search / Access when applicable), and the
// AccountMenu (user badge dropdown with API Keys + Sign out).
//
// Tab visibility:
//   Pipeline / Documents / Search — always when a collection is active.
//   Access — only when the current user is admin on the active collection
//             (or root, who is implicitly admin everywhere).
//
// All colors from CSS vars (token-driven). No hardcoded color values.

// ====== Third-Party Library Imports ======
import { ReactNode } from 'react'

// ====== Internal Project Imports ======
import { ThemeToggle } from '../ui/ThemeToggle'
import { AccountMenu } from './AccountMenu'
import type { GlobalView } from './NavRail'

// ── Types ────────────────────────────────────────────────────────────────────

/** Sub-tabs available within a collection context. */
export type CollectionTab = 'pipeline' | 'documents' | 'search' | 'access'

interface ContextBarProps {
  /** Active global view (determines title + whether sub-tabs appear). */
  activeView: GlobalView
  /** Currently selected collection ID (null if none). */
  activeCollectionId: string | null
  /** Active sub-tab within a collection. */
  activeTab: CollectionTab
  /** Called when the user clicks a collection sub-tab. */
  onTabChange: (tab: CollectionTab) => void
  /** Authenticated username to display in the badge. */
  username: string
  /** Whether the active session is root (controls role pill in AccountMenu). */
  isRoot: boolean
  /**
   * Whether the current user holds admin rights on the active collection.
   * When true, the "Access" sub-tab is rendered.
   */
  isCollectionAdmin: boolean
  /** Right-side action slot (optional additional controls). */
  actions?: ReactNode
}

// ── Constants ─────────────────────────────────────────────────────────────────

/** Base tabs always shown in a collection context. */
const BASE_TABS: { key: CollectionTab; label: string }[] = [
  { key: 'pipeline',  label: 'Pipeline'  },
  { key: 'documents', label: 'Documents' },
  { key: 'search',    label: 'Search'    },
]

/** "Access" tab — shown when the user is admin on the collection. */
const ACCESS_TAB: { key: CollectionTab; label: string } = {
  key: 'access',
  label: 'Access',
}

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
 * Left side:  collection name (or view title for admin / observability).
 * Center:     collection sub-tabs — Pipeline, Documents, Search, and
 *             conditionally Access (when isCollectionAdmin is true).
 * Right side: optional extra actions, AccountMenu, ThemeToggle.
 *
 * Args:
 *   activeView:         Determines title and whether sub-tabs appear.
 *   activeCollectionId: Controls sub-tab visibility.
 *   activeTab:          Currently highlighted sub-tab.
 *   onTabChange:        Sub-tab click callback.
 *   username:           Badge display name.
 *   isRoot:             Controls role pill in AccountMenu.
 *   isCollectionAdmin:  Shows the "Access" tab when true.
 *   actions:            Optional right-side controls.
 */
export function ContextBar({
  activeView,
  activeCollectionId,
  activeTab,
  onTabChange,
  username,
  isRoot,
  isCollectionAdmin,
  actions,
}: ContextBarProps) {
  // 1. Determine whether the collection sub-tabs should be shown.
  const isCollectionView = activeCollectionId !== null
    && activeView !== 'admin'
    && activeView !== 'observability'

  // 2. Build the tab list — add Access tab when the user is a collection admin.
  const tabs = isCollectionAdmin
    ? [...BASE_TABS, ACCESS_TAB]
    : BASE_TABS

  // 3. Resolve the title shown on the left side.
  const title = isCollectionView
    ? activeCollectionId
    : VIEW_LABEL[activeView]

  return (
    <div className="app-header">
      {/* ── Left: view / collection title ── */}
      <span
        className="app-header-collection"
        style={{
          flexShrink: 0,
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          maxWidth: 200,
        }}
      >
        {title ?? 'Select a collection'}
      </span>

      {/* ── Center: collection sub-tabs ── */}
      {isCollectionView && (
        <nav className="app-tabs">
          {tabs.map(tab => (
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

      {/* ── Right: optional actions + AccountMenu + ThemeToggle ── */}
      <div
        className="app-header-end"
        style={{ display: 'flex', alignItems: 'center', gap: 8 }}
      >
        {actions}
        <AccountMenu username={username} isRoot={isRoot} />
        <ThemeToggle />
      </div>
    </div>
  )
}
