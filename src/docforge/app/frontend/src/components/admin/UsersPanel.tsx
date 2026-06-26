// ====== Code Summary ======
// UsersPanel — root-only panel to create, list, deactivate, reset passwords,
// and impersonate application users.
// The optional onActAs callback enables the "Act as" button per user row;
// the button is hidden when onActAs is not provided (e.g. while already
// impersonating, to prevent nested impersonation sessions).

// ====== Third-Party Library Imports ======
import { useEffect, useState, FormEvent } from 'react'

// ====== Internal Project Imports ======
import {
  listUsers,
  createUser,
  deleteUser,
  resetUserPassword,
} from '../../api/client'
import type { UserResponse } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface UsersPanelProps {
  /**
   * When provided, each non-root active user row shows an "Act as" button that
   * calls this handler with the user's UUID.  Omit to hide the button (e.g.
   * when the session is already impersonating to block nested impersonation).
   */
  onActAs?: (userId: string) => Promise<void>
  /** The currently authenticated user's UUID — prevents self-impersonation. */
  currentUserId?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Root-only panel for managing application users.
 *
 * Sections:
 *   1. Create user form — username, password, role selector.
 *   2. User list — rows with username, role, status, deactivate button,
 *      inline password-reset form, and an optional "Act as" impersonation button.
 *
 * Args:
 *   onActAs:       Optional impersonation callback.  When provided, non-root
 *                  active user rows gain an "Act as" button.
 *   currentUserId: The logged-in user's UUID, used to suppress self-impersonation.
 */
export function UsersPanel({ onActAs, currentUserId }: UsersPanelProps) {
  const [users, setUsers] = useState<UserResponse[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  // Create form state.
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole] = useState<'root' | 'user'>('user')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Per-user UI state.
  const [deactivatingId, setDeactivatingId] = useState<string | null>(null)
  const [resetUserId, setResetUserId] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)

  // Per-user impersonation loading state.
  const [actingAsId, setActingAsId] = useState<string | null>(null)
  const [actAsError, setActAsError] = useState<string | null>(null)

  // 1. Load users on mount.
  useEffect(() => {
    void loadUsers()
  }, [])

  async function loadUsers(): Promise<void> {
    try {
      const res = await listUsers()
      setUsers(res.users)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load users.')
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Creates a new user with the form values then refreshes the list.
   *
   * Args:
   *   e: Form submit event.
   */
  async function handleCreate(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      await createUser(newUsername.trim(), newPassword, newRole)
      setNewUsername('')
      setNewPassword('')
      setNewRole('user')
      await loadUsers()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create user.')
    } finally {
      setCreating(false)
    }
  }

  /**
   * Soft-deactivates a user and removes them from the list.
   *
   * Args:
   *   userId: UUID of the user to deactivate.
   */
  async function handleDeactivate(userId: string): Promise<void> {
    setDeactivatingId(userId)
    try {
      await deleteUser(userId)
      setUsers(prev => prev.filter(u => u.id !== userId))
    } catch {
      // Non-fatal — button re-enables automatically.
    } finally {
      setDeactivatingId(null)
    }
  }

  /**
   * Resets a user's password, then hides the inline form.
   *
   * Args:
   *   e: Form submit event.
   */
  async function handleResetPassword(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    if (!resetUserId) return
    setResetting(true)
    setResetError(null)
    try {
      await resetUserPassword(resetUserId, resetPassword)
      setResetUserId(null)
      setResetPassword('')
    } catch (err) {
      setResetError(err instanceof Error ? err.message : 'Failed to reset password.')
    } finally {
      setResetting(false)
    }
  }

  /**
   * Initiates an impersonation session as the given user.
   *
   * Delegates to the onActAs callback provided by the parent (AdminView).
   * Disabled when already acting as someone, or for self / root users.
   *
   * Args:
   *   userId: UUID of the user to impersonate.
   */
  async function handleActAs(userId: string): Promise<void> {
    if (!onActAs) return
    setActingAsId(userId)
    setActAsError(null)
    try {
      await onActAs(userId)
    } catch (err) {
      setActAsError(err instanceof Error ? err.message : 'Impersonation failed.')
      setActingAsId(null)
    }
    // Leave actingAsId set — the app context switches and this panel unmounts.
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  /**
   * Returns true when the "Act as" button should be shown for a given user.
   *
   * Conditions: onActAs is provided, user is not self, user is not root,
   * and user is active.
   *
   * Args:
   *   u: The user row to evaluate.
   */
  function canActAs(u: UserResponse): boolean {
    return (
      onActAs != null
      && u.id !== currentUserId
      && u.role !== 'root'
      && u.is_active
    )
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="admin-section">
      <div className="admin-section-title">Users</div>

      {/* Create form */}
      <form className="admin-create-form" onSubmit={(e) => { void handleCreate(e) }}>
        <div className="admin-create-row">
          <input
            type="text"
            className="input admin-name-input"
            placeholder="Username"
            value={newUsername}
            onChange={e => setNewUsername(e.target.value)}
            required
          />
          <input
            type="password"
            className="input admin-name-input"
            placeholder="Initial password"
            value={newPassword}
            onChange={e => setNewPassword(e.target.value)}
            required
          />
          <select
            className="input select"
            value={newRole}
            onChange={e => setNewRole(e.target.value as 'root' | 'user')}
          >
            <option value="user">user</option>
            <option value="root">root</option>
          </select>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={creating || !newUsername.trim() || !newPassword}
          >
            {creating ? 'Creating...' : 'Create user'}
          </button>
        </div>
        {createError && <div className="error-banner">{createError}</div>}
      </form>

      {/* Act-as error */}
      {actAsError && <div className="error-banner">{actAsError}</div>}

      {/* User list */}
      {loadError && <div className="error-banner">{loadError}</div>}
      {users.length === 0 && !loadError && (
        <p className="text-muted" style={{ marginTop: 12, fontSize: 13 }}>No users found.</p>
      )}

      {users.map(u => (
        <div key={u.id} className="admin-user-row">
          <div className="admin-user-info">
            <span className="admin-user-name">{u.username}</span>
            <span className={`admin-user-role-badge${u.role === 'root' ? ' admin-role-root' : ''}`}>
              {u.role}
            </span>
            {!u.is_active && (
              <span className="tag tag-error">deactivated</span>
            )}
            <span className="text-dim" style={{ fontSize: 11 }}>
              {new Date(u.created_at).toLocaleDateString()}
            </span>
          </div>

          <div className="admin-user-actions">
            {/* Act as — only for eligible users when onActAs is provided. */}
            {canActAs(u) && (
              <button
                type="button"
                className="btn"
                disabled={actingAsId === u.id}
                onClick={() => { void handleActAs(u.id) }}
                title={`Act as ${u.username}`}
              >
                {actingAsId === u.id ? 'Switching...' : 'Act as'}
              </button>
            )}

            <button
              type="button"
              className="btn"
              onClick={() => {
                setResetUserId(prev => prev === u.id ? null : u.id)
                setResetPassword('')
                setResetError(null)
              }}
            >
              Reset password
            </button>

            <button
              type="button"
              className="btn btn-danger"
              disabled={deactivatingId === u.id || !u.is_active}
              onClick={() => { void handleDeactivate(u.id) }}
            >
              {deactivatingId === u.id ? 'Deactivating...' : 'Deactivate'}
            </button>
          </div>

          {/* Inline password reset form */}
          {resetUserId === u.id && (
            <form
              className="admin-reset-form"
              onSubmit={(e) => { void handleResetPassword(e) }}
            >
              <input
                type="password"
                className="input"
                placeholder="New password"
                value={resetPassword}
                onChange={e => setResetPassword(e.target.value)}
                required
                autoFocus
              />
              <button
                type="submit"
                className="btn btn-primary"
                disabled={resetting || !resetPassword}
              >
                {resetting ? 'Saving...' : 'Save'}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => { setResetUserId(null); setResetPassword('') }}
              >
                Cancel
              </button>
              {resetError && <div className="error-banner">{resetError}</div>}
            </form>
          )}
        </div>
      ))}
    </div>
  )
}
