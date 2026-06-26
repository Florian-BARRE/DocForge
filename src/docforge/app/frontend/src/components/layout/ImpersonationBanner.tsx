// ====== Code Summary ======
// ImpersonationBanner — a prominent warning bar rendered at the top of the
// cockpit shell while root is acting as another user.
// Shows the impersonated username and an "Exit" button.
// Reads auth state directly from useAuth() — no props needed.

// ====== Internal Project Imports ======
import { useAuth } from '../../auth/AuthContext'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Full-width warning bar shown whenever the session is impersonating a user.
 *
 * Renders nothing when isImpersonating is false.  The "Exit impersonation"
 * button calls exitImpersonation() which restores the original root session.
 */
export function ImpersonationBanner() {
  const { isImpersonating, impersonatedUser, exitImpersonation } = useAuth()

  // 1. No impersonation in progress — render nothing.
  if (!isImpersonating || !impersonatedUser) return null

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="impersonation-banner" role="alert" aria-live="polite">
      <span style={{ fontWeight: 600 }}>Acting as</span>

      <span className="impersonation-banner-user">
        {impersonatedUser.username}
      </span>

      <span className="impersonation-banner-note">
        — all actions run as this user
      </span>

      <button
        type="button"
        className="btn btn-primary"
        onClick={() => { void exitImpersonation() }}
        style={{ padding: '2px 10px', fontSize: 11, marginLeft: 4 }}
      >
        Exit impersonation
      </button>
    </div>
  )
}
