// ====== Code Summary ======
// AuthContext — holds the authenticated session (token + user) and exposes
// login / logout actions.
//
// AUTH-B simplified model: one root account only.  Grants, impersonation, and
// the actAs/exitImpersonation surface have been removed.  The context is now a
// thin session wrapper: token persisted in localStorage, /auth/me called on
// mount to rehydrate, 401 → force-logout.

// ====== Third-Party Library Imports ======
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { UserSummary } from '../api/types'
import { setAuthToken, setUnauthorizedHandler } from '../api/client'

// ── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'docforge.auth.token'

// ── Types ────────────────────────────────────────────────────────────────────

/**
 * Shape of the value provided by AuthContext.
 *
 * - `token`   — current bearer token, or null when logged out.
 * - `user`    — the authenticated user summary, or null.
 * - `loading` — true while the initial /auth/me rehydration is in flight.
 * - `login`   — async action; throws on bad credentials.
 * - `logout`  — synchronous; clears state and localStorage.
 */
export interface AuthState {
  token: string | null
  user: UserSummary | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

// ── Context ───────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthState | null>(null)

// ── Provider ──────────────────────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode
}

/**
 * Wraps the application and provides authentication state to all descendants.
 *
 * On mount, reads any stored token from localStorage and calls /auth/me to
 * validate it and rehydrate the user.  A 401 response clears the stale token.
 *
 * Args:
 *   children: React subtree that can consume AuthContext.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  // 1. Initialise from localStorage — may be stale; will be validated on mount.
  const [token, setToken] = useState<string | null>(() =>
    window.localStorage.getItem(STORAGE_KEY),
  )
  const [user, setUser] = useState<UserSummary | null>(null)
  // Rehydration is in-flight until /auth/me resolves or we have no token.
  const [loading, setLoading] = useState<boolean>(true)

  // 2. Register the unauthorized handler once so any API call can force-logout.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession()
    })
    // This effect runs only once — clearSession is stable via function hoisting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 3. Keep the api/client token in sync whenever it changes.
  useEffect(() => {
    setAuthToken(token)
  }, [token])

  // 4. Rehydrate on mount from a stored token.
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (!stored) {
      setLoading(false)
      return
    }

    async function rehydrate() {
      try {
        const res = await fetch('/api/v1/auth/me', {
          headers: { Authorization: `Bearer ${stored}` },
        })
        if (res.status === 401) {
          clearSession()
          return
        }
        if (!res.ok) {
          clearSession()
          return
        }
        const data = await res.json()
        setAuthToken(stored)
        setUser(data.user)
        setToken(stored)
      } catch {
        clearSession()
      } finally {
        setLoading(false)
      }
    }

    void rehydrate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Internal helpers ──────────────────────────────────────────────────────

  /**
   * Clears all session state.
   */
  function clearSession(): void {
    setAuthToken(null)
    setToken(null)
    setUser(null)
    try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* quota guard */ }
  }

  // ── Public actions ────────────────────────────────────────────────────────

  /**
   * Authenticates with username + password and stores the resulting token.
   * Throws an Error with a human-readable message when credentials are wrong.
   *
   * Args:
   *   username: The login handle.
   *   password: The plaintext password.
   */
  const login = useCallback(async (username: string, password: string): Promise<void> => {
    // 1. POST credentials to the login endpoint.
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    if (res.status === 401) throw new Error('Invalid username or password.')
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const msg = body?.detail ?? `HTTP ${res.status}`
      throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }

    // 2. Persist token and update user state.
    const data = await res.json()
    const newToken: string = data.access_token
    setAuthToken(newToken)
    try { window.localStorage.setItem(STORAGE_KEY, newToken) } catch { /* quota guard */ }
    setToken(newToken)
    setUser(data.user)
  }, [])

  /**
   * Logs the current user out by clearing all session state.
   */
  const logout = useCallback((): void => {
    clearSession()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Provide ───────────────────────────────────────────────────────────────

  const value: AuthState = {
    token,
    user,
    loading,
    login,
    logout,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the current authentication state from the nearest AuthProvider.
 *
 * Throws if called outside of an AuthProvider — this is an invariant violation.
 *
 * Returns:
 *   AuthState: Token, user, loading flag, and all auth actions.
 */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
