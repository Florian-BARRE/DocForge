// ====== Code Summary ======
// CollectionAccessPanel — manages per-collection collaborators (GitHub-style).
// Lists current grants, lets admins set a user's role or revoke their access.
// Visible only when a collection is selected and the current user is an admin
// on that collection (or is root).

// ====== Third-Party Library Imports ======
import { useEffect, useState, FormEvent } from 'react'

// ====== Internal Project Imports ======
import {
  listCollectionAccess,
  listUsers,
  setCollectionAccess,
  revokeCollectionAccess,
} from '../../api/client'
import type { AccessGrantResponse, UserResponse } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface CollectionAccessPanelProps {
  /** The collection whose collaborators are being managed. */
  collectionId: string
}

type GrantRole = 'read' | 'write' | 'admin'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Collaborator management panel for a single collection.
 *
 * Sections:
 *   1. Grant list — collaborators with role badge and revoke button.
 *   2. Add collaborator form — user picker + role selector.
 *
 * Args:
 *   collectionId: The collection to manage.
 */
export function CollectionAccessPanel({ collectionId }: CollectionAccessPanelProps) {
  const [grants, setGrants] = useState<AccessGrantResponse[]>([])
  const [users, setUsers] = useState<UserResponse[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  // Add-collaborator form state.
  const [addUserId, setAddUserId] = useState('')
  const [addRole, setAddRole] = useState<GrantRole>('read')
  const [adding, setAdding] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  // Per-row action state.
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [updatingId, setUpdatingId] = useState<string | null>(null)

  // 1. Load grants and users when the collection changes.
  useEffect(() => {
    void loadData()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId])

  async function loadData(): Promise<void> {
    try {
      const [accessRes, usersRes] = await Promise.all([
        listCollectionAccess(collectionId),
        listUsers(),
      ])
      setGrants(accessRes.grants)
      setUsers(usersRes.users)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load access data.')
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Adds a new collaborator or updates an existing one's role.
   *
   * Args:
   *   e: Form submit event.
   */
  async function handleAdd(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    if (!addUserId) return
    setAdding(true)
    setAddError(null)
    try {
      await setCollectionAccess(collectionId, addUserId, addRole)
      setAddUserId('')
      setAddRole('read')
      await loadData()
    } catch (err) {
      setAddError(err instanceof Error ? err.message : 'Failed to set access.')
    } finally {
      setAdding(false)
    }
  }

  /**
   * Changes an existing grant's role in-place.
   *
   * Args:
   *   userId: The user whose role is being changed.
   *   role:   The new role.
   */
  async function handleChangeRole(userId: string, role: GrantRole): Promise<void> {
    setUpdatingId(userId)
    try {
      await setCollectionAccess(collectionId, userId, role)
      setGrants(prev => prev.map(g => g.user_id === userId ? { ...g, role } : g))
    } catch {
      // Role change failure — silently revert by reloading.
      await loadData()
    } finally {
      setUpdatingId(null)
    }
  }

  /**
   * Revokes a collaborator's grant.
   *
   * Args:
   *   userId: The user whose grant is being revoked.
   */
  async function handleRevoke(userId: string): Promise<void> {
    setRevokingId(userId)
    try {
      await revokeCollectionAccess(collectionId, userId)
      setGrants(prev => prev.filter(g => g.user_id !== userId))
    } catch {
      // Revoke failure is silent — button re-enables.
    } finally {
      setRevokingId(null)
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  /** Returns users who do not yet have a grant on this collection. */
  function ungrantedUsers(): UserResponse[] {
    const grantedIds = new Set(grants.map(g => g.user_id))
    return users.filter(u => !grantedIds.has(u.id) && u.is_active)
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const available = ungrantedUsers()

  return (
    <div className="admin-section">
      <div className="admin-section-title">Collaborators</div>

      {loadError && <div className="error-banner">{loadError}</div>}

      {/* Grant list */}
      {grants.length === 0 && !loadError && (
        <p className="text-muted" style={{ marginTop: 12, fontSize: 13 }}>
          No collaborators yet. Add one below.
        </p>
      )}
      {grants.map(g => (
        <div key={g.user_id} className="admin-grant-row">
          <span className="admin-grant-username">{g.username ?? g.user_id}</span>
          <select
            className="input select admin-role-select"
            value={g.role}
            disabled={updatingId === g.user_id}
            onChange={e => {
              void handleChangeRole(g.user_id, e.target.value as GrantRole)
            }}
          >
            <option value="read">read</option>
            <option value="write">write</option>
            <option value="admin">admin</option>
          </select>
          <button
            type="button"
            className="btn btn-danger"
            disabled={revokingId === g.user_id}
            onClick={() => { void handleRevoke(g.user_id) }}
          >
            {revokingId === g.user_id ? 'Revoking...' : 'Revoke'}
          </button>
        </div>
      ))}

      {/* Add collaborator form */}
      <form
        className="admin-create-row"
        style={{ marginTop: 16 }}
        onSubmit={(e) => { void handleAdd(e) }}
      >
        <select
          className="input select admin-name-input"
          value={addUserId}
          onChange={e => setAddUserId(e.target.value)}
          required
        >
          <option value="">Select a user...</option>
          {available.map(u => (
            <option key={u.id} value={u.id}>{u.username}</option>
          ))}
        </select>
        <select
          className="input select"
          value={addRole}
          onChange={e => setAddRole(e.target.value as GrantRole)}
        >
          <option value="read">read</option>
          <option value="write">write</option>
          <option value="admin">admin</option>
        </select>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={adding || !addUserId}
        >
          {adding ? 'Adding...' : 'Add'}
        </button>
      </form>
      {addError && <div className="error-banner">{addError}</div>}
    </div>
  )
}
