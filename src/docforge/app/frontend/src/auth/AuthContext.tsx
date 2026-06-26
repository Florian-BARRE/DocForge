// ====== Code Summary ======
// AuthContext — holds the authenticated session (token + user + grants) and
// exposes login / logout / actAs / exitImpersonation actions.
// Token is persisted to localStorage so it survives page reloads.
// On mount, if a stored token exists, /auth/me is called to rehydrate the
// user; a 401 response force-logs out.
//
// Impersonation (root only):
//   actAs(userId)        — stash the root token in-memory, swap the
//                          impersonation token, refetch /auth/me as target.
//   exitImpersonation()  — restore the stashed root token, refetch /auth/me
//                          as root.
//   isImpersonating      — true while a stash is held.
//   impersonatedUser     — the currently impersonated UserSummary, or null.

// ====== Third-Party Library Imports ======
import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import type { ReactNode } from 'react'

// ====== Internal Project Imports ======
import type { UserSummary, CollectionGrantSummary } from '../api/types'
import { setAuthToken, setUnauthorizedHandler, impersonateUser } from '../api/client'

// ── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'docforge.auth.token'

// ── Types ────────────────────────────────────────────────────────────────────

/**
 * Shape of the value provided by AuthContext.
 *
 * - `token`           — current bearer token, or null when logged out.
 * - `user`            — the authenticated user summary, or null.
 * - `grants`          — per-collection grants for the current user.
 * - `loading`         — true while the initial /auth/me rehydration is in flight.
 * - `isImpersonating` — true while the root session is impersonating another user.
 * - `impersonatedUser`— the user being acted as (same as `user` when impersonating).
 * - `login`           — async action; throws on bad credentials.
 * - `logout`          — synchronous; clears state and localStorage.
 * - `actAs`           — async; switches to an impersonation session (root only).
 * - `exitImpersonation` — async; restores the original root session.
 */
export interface AuthState {
  token: string | null
  user: UserSummary | null
  grants: CollectionGrantSummary[]
  loading: boolean
  isImpersonating: boolean
  impersonatedUser: UserSummary | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  actAs: (userId: string) => Promise<void>
  exitImpersonation: () => Promise<void>
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
  // Rehydration is in-flight until /auth/me resolves or we have no token.
  const [loading, setLoading] = useState<boolean>(true)

  // In-memory stash of the root token while impersonating another user.
  // Not persisted to localStorage — a page reload ends the impersonation session.
  const [stashedToken, setStashedToken] = useState<string | null>(null)

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
        setGrants(data.grants ?? [])
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
   * Clears all session state, including any active impersonation stash.
   */
  function clearSession(): void {
    setAuthToken(null)
    setToken(null)
    setUser(null)
    setGrants([])
    setStashedToken(null)
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

  /**
   * Switches the session to act as a different user (root only).
   *
   * Stashes the current root token in-memory, then swaps in the impersonation
   * token returned by POST /users/{id}/impersonate.  The entire app behaves as
   * the target user until exitImpersonation() is called.
   *
   * Args:
   *   userId: UUID of the user to impersonate.
   */
  const actAs = useCallback(async (userId: string): Promise<void> => {
    // 1. Request an impersonation token from the backend.
    const res = await impersonateUser(userId)
    const impToken = res.access_token

    // 2. Stash the current (root) token before switching.
    setStashedToken(token)

    // 3. Activate the impersonation token IN-MEMORY ONLY. We deliberately do NOT persist it to
    //    localStorage — the root token stays the persisted one, so a page reload cleanly returns
    //    to the root session (impersonation never survives a reload, and root can never get
    //    "stuck" as the impersonated user).
    setAuthToken(impToken)
    setToken(impToken)
    setUser(res.user)

    // 4. Fetch grants for the impersonated user so collection access reflects them.
    try {
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${impToken}` },
      })
      if (meRes.ok) {
        const meData = await meRes.json()
        setGrants(meData.grants ?? [])
      }
    } catch {
      setGrants([])
    }
  }, [token])

  /**
   * Restores the original root session after an impersonation.
   *
   * Clears the stash, reinstates the root token, and refetches /auth/me to
   * restore the root user and grants.
   */
  const exitImpersonation = useCallback(async (): Promise<void> => {
    if (!stashedToken) return

    const rootToken = stashedToken

    // 1. Restore the stashed root token immediately to avoid a gap.
    setStashedToken(null)
    setAuthToken(rootToken)
    try { window.localStorage.setItem(STORAGE_KEY, rootToken) } catch { /* quota guard */ }
    setToken(rootToken)

    // 2. Refetch /auth/me as root to restore user + grants.
    try {
      const meRes = await fetch('/api/v1/auth/me', {
        headers: { Authorization: `Bearer ${rootToken}` },
      })
      if (meRes.ok) {
        const meData = await meRes.json()
        setUser(meData.user)
        setGrants(meData.grants ?? [])
      } else {
        // Root token expired during impersonation — force logout.
        clearSession()
      }
    } catch {
      clearSession()
    }
  }, [stashedToken])

  // ── Derived state ─────────────────────────────────────────────────────────

  // isImpersonating is true whenever a root token stash is held.
  const isImpersonating = stashedToken !== null
  // impersonatedUser mirrors `user` during an impersonation session.
  const impersonatedUser = isImpersonating ? user : null

  // ── Provide ───────────────────────────────────────────────────────────────

  const value: AuthState = {
    token,
    user,
    grants,
    loading,
    isImpersonating,
    impersonatedUser,
    login,
    logout,
    actAs,
    exitImpersonation,
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
 *   AuthState: Token, user, grants, loading flag, and all auth actions.
 */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
