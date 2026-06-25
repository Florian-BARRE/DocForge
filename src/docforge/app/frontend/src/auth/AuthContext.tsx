// ====== Code Summary ======
// AuthContext — holds the authenticated session (token + user) and exposes
// login() / logout() actions.  Token is persisted to localStorage so it
// survives page reloads.  On mount, if a stored token exists, /auth/me is
// called to rehydrate the user object; a 401 response force-logs out.

// ====== Third-Party Library Imports ======
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { UserSummary, CollectionGrantSummary } from '../api/types'
import { setAuthToken, setUnauthorizedHandler } from '../api/client'

// ── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'docforge.auth.token'

// ── Types ────────────────────────────────────────────────────────────────────

/**
 * Shape of the value provided by AuthContext.
 *
 * - `token`  — current bearer token, or null when logged out.
 * - `user`   — the authenticated user summary, or null.
 * - `grants` — per-collection grants for the current user (empty for root).
 * - `loading` — true while the initial /auth/me rehydration is in flight.
 * - `login`   — async action; throws on bad credentials (callers catch).
 * - `logout`  — synchronous action; clears state and localStorage.
 */
export interface AuthState {
  token: string | null
  user: UserSummary | null
  grants: CollectionGrantSummary[]
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
  const [grants, setGrants] = useState<CollectionGrantSummary[]>([])
  // Rehydration is in-flight until /auth/me resolves or we determine there is no token.
  const [loading, setLoading] = useState<boolean>(true)

  // 2. Register the unauthorized handler once so any API call can force-logout.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clearSession()
    })
    // This effect intentionally runs only once — clearSession is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 3. Keep the api/client token in sync whenever it changes (login / logout / rehydrate).
  useEffect(() => {
    setAuthToken(token)
  }, [token])

  // 5. Rehydrate on mount from a stored token.
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
          // Token is expired or invalid — force logout.
          clearSession()
          return
        }
        if (!res.ok) {
          // Other server errors — treat as logged-out for safety.
          clearSession()
          return
        }
        const data = await res.json()
        // Register synchronously before the app renders its authed subtree (same
        // child-effect-before-parent-effect race as in login()).
        setAuthToken(stored)
        setUser(data.user)
        setGrants(data.grants ?? [])
        setToken(stored)
      } catch {
        // Network error on mount — clear state so the login screen shows.
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
   * Clears all session state and removes the token from localStorage.
   */
  function clearSession(): void {
    setAuthToken(null)
    setToken(null)
    setUser(null)
    setGrants([])
    try { window.localStorage.removeItem(STORAGE_KEY) } catch { /* quota guard */ }
  }

  // ── Public actions ────────────────────────────────────────────────────────

  /**
   * Authenticates with username + password and stores the resulting token.
   * Throws an Error with a human-readable message when credentials are wrong
   * or the server returns an unexpected status.
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
    // Register the token in the api/client SYNCHRONOUSLY — React runs child effects
    // before the parent provider's [token] effect, so a child's first request() would
    // otherwise fire before setAuthToken ran, 401, and bounce us back to login.
    setAuthToken(newToken)
    try { window.localStorage.setItem(STORAGE_KEY, newToken) } catch { /* quota guard */ }
    setToken(newToken)
    setUser(data.user)

    // 3. Fetch grants via /auth/me (login response does not include grants).
    try {
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${newToken}` },
      })
      if (meRes.ok) {
        const meData = await meRes.json()
        setGrants(meData.grants ?? [])
      }
    } catch {
      // Grants fetch failure is non-fatal; access control will be conservative.
    }
  }, [])

  /**
   * Logs the current user out by clearing all session state.
   */
  const logout = useCallback((): void => {
    clearSession()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Provide ───────────────────────────────────────────────────────────────

  const value: AuthState = { token, user, grants, loading, login, logout }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * Returns the current authentication state from the nearest AuthProvider.
 *
 * Throws if called outside of an AuthProvider — this is an invariant violation.
 *
 * Returns:
 *   AuthState: The current token, user, grants, loading flag and auth actions.
 */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
