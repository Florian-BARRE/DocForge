// ====== Code Summary ======
// NavRail — the persistent left vertical rail in the cockpit shell.
// Contains: DocForge logo, global nav entries (Pipeline/Documents/Search/
// Observability/API Keys), and the collections list below the nav.
// All colors from CSS vars (token-driven). No hardcoded color values.
// Typography: Inter (var(--font-ui)) everywhere — no mono for labels/nav.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { listCollections } from '../../api/client'
import type { Collection } from '../../api/types'
import { StatusDot } from '../ui/primitives/StatusDot'

// ── Types ────────────────────────────────────────────────────────────────────

export type GlobalView = 'pipeline' | 'documents' | 'search' | 'observability' | 'apikeys'

interface NavRailProps {
  /** Currently active global view. */
  activeView: GlobalView
  /** Currently selected collection ID. */
  activeCollectionId: string | null
  /** Called when the user selects a collection. */
  onSelectCollection: (id: string) => void
  /** Called when the user clicks "+ New Collection". */
  onNew: () => void
  /** Called when a global nav entry is clicked. */
  onNavigate: (view: GlobalView) => void
  /** Whether to show the API Keys nav entry (root only). */
  showApiKeys: boolean
}

// ── Constants ─────────────────────────────────────────────────────────────────

const NAV_ENTRIES: { key: GlobalView; icon: string; label: string }[] = [
  { key: 'pipeline',      icon: '⚙',  label: 'Pipeline'     },
  { key: 'documents',     icon: '📄',  label: 'Documents'    },
  { key: 'search',        icon: '🔍',  label: 'Search'       },
  { key: 'observability', icon: '📊',  label: 'Observability'},
]

// ── Helpers ──────────────────────────────────────────────────────────────────

function docCount(col: Collection): number {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (col as any).stats?.doc_count ?? 0
}

function hasProcessedDocs(col: Collection): boolean {
  return docCount(col) > 0
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Persistent left navigation rail for the cockpit shell.
 *
 * Renders two sections:
 *   - Global nav: fixed entries for each major zone.
 *   - Collections: scrollable list of user collections with status dots.
 *
 * Polls the collection list every 5 s so count badges stay current.
 * All labels use Inter (--font-ui), never mono.
 *
 * Args:
 *   activeView: Highlighted global nav entry.
 *   activeCollectionId: Highlighted collection row.
 *   onSelectCollection: Collection row click handler.
 *   onNew: New collection button handler.
 *   onNavigate: Global nav entry click handler.
 *   showApiKeys: Whether to show the API Keys nav entry (root only).
 */
export function NavRail({
  activeView,
  activeCollectionId,
  onSelectCollection,
  onNew,
  onNavigate,
  showApiKeys,
}: NavRailProps) {
  const [collections, setCollections] = useState<Collection[]>([])

  // 1. Poll collections every 5 s.
  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await listCollections()
        if (!cancelled) setCollections(res.collections)
      } catch { /* silently ignore transient errors */ }
    }

    void poll()
    const id = setInterval(() => { void poll() }, 5000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  return (
    <aside style={{
      width: 'var(--sidebar-w)',
      minWidth: 'var(--sidebar-w)',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: 'var(--surface)',
      borderRight: '1px solid var(--border)',
      overflow: 'hidden',
    }}>

      {/* ── Logo — Inter 700, accent-colored, premium tracking ── */}
      <div style={{
        height: 'var(--topbar-h)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
      }}>
        <span style={{
          fontSize: 15,
          fontWeight: 700,
          fontFamily: 'var(--font-ui)',
          color: 'var(--accent)',
          letterSpacing: '-0.01em',
        }}>
          DocForge
        </span>
      </div>

      {/* ── Global nav entries — comfortable height, accent-soft active state ── */}
      <nav style={{ padding: '8px 0', flexShrink: 0 }}>
        {NAV_ENTRIES.map(entry => (
          <NavEntry
            key={entry.key}
            icon={entry.icon}
            label={entry.label}
            active={activeView === entry.key}
            onClick={() => onNavigate(entry.key)}
          />
        ))}
        {showApiKeys && (
          <NavEntry
            icon="🔑"
            label="API Keys"
            active={activeView === 'apikeys'}
            onClick={() => onNavigate('apikeys')}
          />
        )}
      </nav>

      {/* ── Collections section ── */}
      <div style={{
        borderTop: '1px solid var(--border)',
        paddingTop: 4,
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
        minHeight: 0,
      }}>
        {/* Section label — Inter, muted text, refined tracking */}
        <div style={{
          padding: '8px 14px 4px',
          fontSize: 11,
          fontWeight: 600,
          fontFamily: 'var(--font-ui)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--text-muted)',
          flexShrink: 0,
        }}>
          Collections
        </div>

        {/* Scrollable list */}
        <ul
          role="listbox"
          aria-label="Collections"
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '2px 0',
            margin: 0,
            listStyle: 'none',
          }}
        >
          {collections.map(col => {
            const isActive = col.id === activeCollectionId
            const done     = hasProcessedDocs(col)
            const count    = docCount(col)
            return (
              <li
                key={col.id}
                role="option"
                aria-selected={isActive}
                onClick={() => onSelectCollection(col.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 12px 6px 14px',
                  cursor: 'pointer',
                  // Left accent bar is the primary active indicator.
                  borderLeft: `3px solid ${isActive ? 'var(--accent)' : 'transparent'}`,
                  background: isActive ? 'var(--accent-soft)' : 'transparent',
                  transition: 'background 0.12s',
                  userSelect: 'none',
                }}
                onMouseEnter={e => {
                  if (!isActive) (e.currentTarget as HTMLElement).style.background = 'var(--hover)'
                }}
                onMouseLeave={e => {
                  if (!isActive) (e.currentTarget as HTMLElement).style.background = 'transparent'
                }}
              >
                <StatusDot
                  status={done ? 'done' : 'idle'}
                  size={6}
                  title={done ? 'Has processed documents' : 'No processed documents'}
                />
                {/* Collection name — Inter, full contrast on active, muted otherwise */}
                <span style={{
                  flex: 1,
                  fontSize: 'var(--text-base)',
                  fontFamily: 'var(--font-ui)',
                  fontWeight: isActive ? 500 : 400,
                  color: isActive ? 'var(--text)' : 'var(--text-muted)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  minWidth: 0,
                }}>
                  {col.name}
                </span>
                {/* Count badge — Inter (not mono), subtle background */}
                {count > 0 && (
                  <span style={{
                    fontSize: 11,
                    fontFamily: 'var(--font-ui)',
                    fontWeight: 500,
                    color: 'var(--text-dim)',
                    padding: '1px 6px',
                    borderRadius: 'var(--radius-full)',
                    background: 'var(--surface-raised)',
                    border: '1px solid var(--border)',
                    flexShrink: 0,
                    lineHeight: 1.4,
                  }}>
                    {count}
                  </span>
                )}
              </li>
            )
          })}
          {collections.length === 0 && (
            <li style={{
              padding: '8px 14px',
              fontSize: 'var(--text-base)',
              fontFamily: 'var(--font-ui)',
              color: 'var(--text-dim)',
              pointerEvents: 'none',
            }}>
              No collections
            </li>
          )}
        </ul>

        {/* New collection footer button */}
        <div style={{
          padding: '10px 12px',
          borderTop: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <button
            type="button"
            onClick={onNew}
            style={{
              width: '100%',
              padding: '7px 10px',
              fontSize: 'var(--text-base)',
              fontFamily: 'var(--font-ui)',
              fontWeight: 500,
              color: 'var(--accent)',
              background: 'var(--accent-soft)',
              border: '1px solid transparent',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'background 0.12s, border-color 0.12s',
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent)'
              ;(e.currentTarget as HTMLElement).style.background = 'rgba(99,102,241,0.22)'
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = 'transparent'
              ;(e.currentTarget as HTMLElement).style.background = 'var(--accent-soft)'
            }}
          >
            + New Collection
          </button>
        </div>
      </div>
    </aside>
  )
}

// ── NavEntry sub-component ────────────────────────────────────────────────────

interface NavEntryProps {
  icon: string
  label: string
  active: boolean
  stub?: boolean
  onClick: () => void
}

/**
 * Single navigation rail entry.
 *
 * Active state: accent-soft background + 3px left accent bar.
 * Uses Inter (--font-ui) for the label — never mono.
 * Height is set via generous padding (8px/10px) for a comfortable 36px tap area.
 *
 * Args:
 *   icon: Emoji/icon character.
 *   label: Display label (Inter font, 500 weight when active).
 *   active: Whether this entry is currently selected.
 *   stub: If true, the zone is not yet built (dims the entry).
 *   onClick: Navigation callback.
 */
function NavEntry({ icon, label, active, stub = false, onClick }: NavEntryProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={stub ? `${label} — coming soon` : label}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 9,
        width: '100%',
        padding: '8px 14px',
        border: 'none',
        borderRadius: 0,
        background: active ? 'var(--accent-soft)' : 'transparent',
        color: active ? 'var(--text)' : stub ? 'var(--text-dim)' : 'var(--text-muted)',
        // Inter label, 500 weight when active for subtle emphasis.
        fontSize: 'var(--text-base)',
        fontFamily: 'var(--font-ui)',
        fontWeight: active ? 500 : 400,
        cursor: stub ? 'default' : 'pointer',
        textAlign: 'left',
        // Left accent bar is the sole active indicator — matches sidebar rows.
        borderLeft: `3px solid ${active ? 'var(--accent)' : 'transparent'}`,
        transition: 'background 0.12s, color 0.12s',
        opacity: stub ? 0.5 : 1,
      }}
      onMouseEnter={e => {
        if (!active && !stub) {
          (e.currentTarget as HTMLElement).style.background = 'var(--hover)'
          ;(e.currentTarget as HTMLElement).style.color = 'var(--text)'
        }
      }}
      onMouseLeave={e => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.background = 'transparent'
          ;(e.currentTarget as HTMLElement).style.color = stub ? 'var(--text-dim)' : 'var(--text-muted)'
        }
      }}
    >
      {/* Icon — slightly larger, fixed width for alignment */}
      <span style={{ fontSize: 14, width: 18, textAlign: 'center', flexShrink: 0, lineHeight: 1 }}>
        {icon}
      </span>
      <span style={{ flex: 1, lineHeight: 1.2 }}>{label}</span>
      {stub && (
        <span style={{
          fontSize: 9,
          fontFamily: 'var(--font-ui)',
          color: 'var(--text-dim)',
          background: 'var(--surface-raised)',
          border: '1px solid var(--border)',
          borderRadius: 3,
          padding: '1px 4px',
          letterSpacing: '0.04em',
        }}>
          SOON
        </span>
      )}
    </button>
  )
}
