// ====== Code Summary ======
// LoginScreen — full-screen login form rendered when no authenticated user
// is present.  Calls useAuth().login() and shows a 401-specific error message.
// Form follows the existing .input / .btn / .btn-primary conventions from global.css.

// ====== Third-Party Library Imports ======
import { useState, FormEvent } from 'react'

// ====== Internal Project Imports ======
import { useAuth } from './AuthContext'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Full-screen centered login form.
 *
 * Displays a username/password form.  On bad credentials (401), shows an
 * inline error message under the inputs.  Submitting while a request is in
 * flight disables the button to prevent double-sends.
 */
export function LoginScreen() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  /**
   * Handles form submission.  Clears any previous error, calls login(), and
   * displays the error message on failure.
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
      setError(err instanceof Error ? err.message : 'Login failed.')
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

          {/* Inline error — shown only on bad credentials */}
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
