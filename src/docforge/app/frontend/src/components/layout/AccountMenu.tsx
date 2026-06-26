// ====== Code Summary ======
// AccountMenu — top-right user badge that doubles as a dropdown trigger.
//
// AUTH-B: API Keys is now a dedicated NavRail page, so the dropdown only
// exposes Sign out.  The drawer holding ApiKeysPanel is removed.
//
// Self-contained: manages dropdown-open state internally.
// Calls useAuth() directly for the logout action (read-only, no permission gate).

// ====== Third-Party Library Imports ======
import { useState, useRef, useEffect } from 'react'

// ====== Internal Project Imports ======
import { useAuth } from '../../auth/AuthContext'

// ── Types ────────────────────────────────────────────────────────────────────

interface AccountMenuProps {
  /** Display name for the badge. */
  username: string
  /** Whether the underlying session is root (shows role pill). */
  isRoot: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * User badge + dropdown in the ContextBar top-right corner.
 *
 * The badge shows the username and an optional "root" pill.  Clicking it
 * opens a small dropdown with a single entry: Sign out.
 *
 * Click-away detection closes the dropdown when the user clicks outside the
 * menu wrapper.
 *
 * Args:
 *   username: Display name shown in the badge.
 *   isRoot:   Controls visibility of the "root" role pill.
 */
export function AccountMenu({ username, isRoot }: AccountMenuProps) {
  const { logout } = useAuth()

  const [menuOpen, setMenuOpen] = useState(false)

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

  // ── Handler ───────────────────────────────────────────────────────────────

  /**
   * Signs the user out and closes the dropdown.
   */
  function handleSignOut(): void {
    setMenuOpen(false)
    logout()
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
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
            minWidth: 140,
            padding: '4px 0',
          }}
        >
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
  )
}
