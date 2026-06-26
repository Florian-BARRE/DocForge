// ====== Code Summary ======
// AccountMenu — top-right user badge that doubles as a dropdown trigger.
// Exposes personal-scope actions available to every authenticated user:
//   - "API Keys"  → opens ApiKeysPanel in a right-edge Drawer.
//   - "Sign out"  → calls logout() from AuthContext.
// Self-contained: manages dropdown-open and drawer-open state internally.
// Calls useAuth() directly for the logout action (read-only, no permission gate).

// ====== Third-Party Library Imports ======
import { useState, useRef, useEffect } from 'react'

// ====== Internal Project Imports ======
import { useAuth } from '../../auth/AuthContext'
import { Drawer } from '../ui/primitives/Drawer'
import { ApiKeysPanel } from '../admin/ApiKeysPanel'

// ── Types ────────────────────────────────────────────────────────────────────

interface AccountMenuProps {
  /** Display name for the badge (may differ from auth user when impersonating). */
  username: string
  /** Whether the underlying session is root (shows role pill). */
  isRoot: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * User badge + dropdown in the ContextBar top-right corner.
 *
 * The badge shows the username and an optional "root" pill.  Clicking it
 * opens a small dropdown with two entries: API Keys (Drawer) and Sign out.
 *
 * Click-away detection closes the dropdown when the user clicks outside the
 * menu wrapper, matching standard dropdown UX.
 *
 * Args:
 *   username: Display name shown in the badge.
 *   isRoot:   Controls visibility of the "root" role pill.
 */
export function AccountMenu({ username, isRoot }: AccountMenuProps) {
  const { logout } = useAuth()

  const [menuOpen, setMenuOpen]   = useState(false)
  const [keysOpen, setKeysOpen]   = useState(false)

  // Ref for click-away detection.
  const wrapperRef = useRef<HTMLDivElement>(null)

  // 1. Close dropdown when the user clicks anywhere outside the wrapper.
  useEffect(() => {
    if (!menuOpen) return

    function handleOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [menuOpen])

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Opens the API Keys Drawer and closes the dropdown.
   */
  function handleOpenKeys(): void {
    setMenuOpen(false)
    setKeysOpen(true)
  }

  /**
   * Signs the user out and closes the dropdown.
   */
  function handleSignOut(): void {
    setMenuOpen(false)
    logout()
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <div ref={wrapperRef} className="account-menu-wrapper">
        {/* Badge / dropdown trigger */}
        <button
          type="button"
          className="account-menu-trigger app-user-badge"
          onClick={() => setMenuOpen(o => !o)}
          title="Account menu"
          aria-haspopup="true"
          aria-expanded={menuOpen}
        >
          <span className="app-user-name">{username}</span>
          {isRoot && <span className="app-user-role">root</span>}
          {/* Chevron indicator */}
          <span style={{
            fontSize: 9,
            color: 'var(--text-dim)',
            marginLeft: 2,
            transform: menuOpen ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.15s',
            display: 'inline-block',
          }}>
            ▾
          </span>
        </button>

        {/* Dropdown panel */}
        {menuOpen && (
          <div
            role="menu"
            style={{
              position: 'absolute',
              right: 0,
              top: 'calc(100% + 6px)',
              background: 'var(--surface-raised)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius)',
              boxShadow: 'var(--shadow-2)',
              zIndex: 'var(--z-dropdown, 100)',
              minWidth: 160,
              padding: '4px 0',
            }}
          >
            <button
              type="button"
              role="menuitem"
              className="account-menu-item"
              onClick={handleOpenKeys}
            >
              API Keys
            </button>

            {/* Separator */}
            <div style={{
              height: 1,
              background: 'var(--border)',
              margin: '4px 0',
            }} />

            <button
              type="button"
              role="menuitem"
              className="account-menu-item account-menu-item-danger"
              onClick={handleSignOut}
            >
              Sign out
            </button>
          </div>
        )}
      </div>

      {/* API keys drawer — mounts outside the dropdown wrapper to avoid clipping. */}
      <Drawer
        isOpen={keysOpen}
        title="My API Keys"
        onClose={() => setKeysOpen(false)}
        width={420}
      >
        <ApiKeysPanel />
      </Drawer>
    </>
  )
}
