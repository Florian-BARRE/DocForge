// ====== Code Summary ======
// LoginScreen — full-screen login form rendered when no authenticated user
// is present.  Calls useAuth().login() and shows a friendly error message.
// 401 → "Invalid username or password." (set by AuthContext).
// Other errors have any leading "Error:" prefix stripped before display.
// Form follows the existing .input / .btn / .btn-primary conventions from global.css.

// ====== Third-Party Library Imports ======
import { useState, FormEvent } from 'react'

// ====== Internal Project Imports ======
import { useAuth } from './AuthContext'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Normalise a caught login error into a display-safe string.
 *
 * Strips any leading "Error:" prefix that may appear in raw API error messages
 * (e.g. when fetch throws before the response is parsed).  AuthContext already
 * sets a human-readable message for 401 ("Invalid username or password."), so
 * this function is mainly a defensive clean-up for edge cases.
 *
 * Args:
 *   err: The caught error value (unknown type).
 *
 * Returns:
 *   A trimmed, display-ready error string.
 */
function formatLoginError(err: unknown): string {
  const raw = err instanceof Error ? err.message : 'Login failed.'
  const clean = raw.replace(/^Error:\s*/i, '').trim()
  return clean || 'Login failed.'
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Full-screen centered login form.
 *
 * Displays a username/password form.  On bad credentials (401), shows the
 * AuthContext-provided "Invalid username or password." message.  Any other
 * error has its leading "Error:" prefix stripped.  Submitting while a request
 * is in flight disables the button to prevent double-sends.
 */
export function LoginScreen() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  /**
   * Handles form submission.  Clears any previous error, calls login(), and
   * displays a friendly error message on failure.
   *
   * Args:
   *   e: The native form submit event (prevents default navigation).
   */
  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(formatLoginError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        {/* Product wordmark */}
        <div className="login-logo">DocForge</div>
        <p className="login-subtitle">Sign in to continue</p>

        <form className="login-form" onSubmit={(e) => { void handleSubmit(e) }}>
          {/* Username field */}
          <div className="login-field">
            <label className="login-label" htmlFor="login-username">
              Username
            </label>
            <input
              id="login-username"
              type="text"
              className="input"
              placeholder="username"
              autoComplete="username"
              autoFocus
              required
              value={username}
              onChange={e => setUsername(e.target.value)}
            />
          </div>

          {/* Password field */}
          <div className="login-field">
            <label className="login-label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              className="input"
              autoComplete="current-password"
              required
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>

          {/* Inline error — shown on failed login */}
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            className="btn btn-primary login-submit"
            disabled={submitting || !username || !password}
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
