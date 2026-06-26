// ====== Code Summary ======
// AdminView — instance-level administration area, root-gated in NavRail.
// Renders UsersPanel with the "Act as" impersonation capability wired in.
//
// Scope split (UI-5):
//   - Personal (API Keys)     → AccountMenu in ContextBar (every user).
//   - Per-collection (Access) → "Access" sub-tab in ContextBar (collection admin).
//   - Instance (Users)        → this view, root-only.

// ====== Internal Project Imports ======
import { useAuth } from '../../auth/AuthContext'
import { UsersPanel } from './UsersPanel'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Instance-level admin area rendered when the "Admin" NavRail entry is active.
 *
 * Gated to root-role sessions — if the current user is not root this view is
 * unreachable (NavRail hides the Admin entry).
 *
 * Exposes UsersPanel with the "Act as" callback wired to actAs() from
 * AuthContext.  The button is hidden automatically by UsersPanel while an
 * impersonation session is already active (prevents nested impersonation).
 */
export function AdminView() {
  const { user, isImpersonating, actAs } = useAuth()

  if (!user) return null

  // Only the real root can reach this view; impersonating sessions will not
  // have the Admin NavRail entry visible, so this is a belt-and-suspenders guard.
  const isRoot = user.role === 'root'
  if (!isRoot) return null

  // Provide the actAs callback only when NOT already impersonating — UsersPanel
  // hides the "Act as" button when the prop is absent, blocking nested sessions.
  const handleActAs = !isImpersonating ? actAs : undefined

  return (
    <div className="admin-view">
      <UsersPanel
        onActAs={handleActAs}
        currentUserId={user.id}
      />
    </div>
  )
}
