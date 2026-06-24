// ====== Code Summary ======
// ApiKeysPanel — lets any authenticated user create, list, and revoke their
// own API keys.  A newly-created key is shown ONCE in a prominent banner with
// a copy button; after the user dismisses it, the plaintext is gone forever.

// ====== Third-Party Library Imports ======
import { useEffect, useState, FormEvent } from 'react'

// ====== Internal Project Imports ======
import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
} from '../../api/client'
import type { ApiKeySummary, ApiKeyCreatedResponse } from '../../api/types'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Panel that manages API keys for the currently authenticated user.
 *
 * Sections:
 *   1. "Create key" form — name input + submit.
 *   2. "Key created" one-time banner — shows the plaintext key with a copy
 *      button; dismissed by the user when they have safely stored the key.
 *   3. Key list — rows with name, prefix, created date, last-used date,
 *      and a revoke button.
 */
export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKeySummary[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  // State for the "create" form.
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // The newly created key — shown ONCE then discarded.
  const [createdKey, setCreatedKey] = useState<ApiKeyCreatedResponse | null>(null)
  const [copied, setCopied] = useState(false)

  // Revoke state per key id.
  const [revokingId, setRevokingId] = useState<string | null>(null)

  // 1. Load keys on mount.
  useEffect(() => {
    void loadKeys()
  }, [])

  async function loadKeys(): Promise<void> {
    try {
      const res = await listApiKeys()
      setKeys(res.keys)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load keys.')
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Creates a new API key with the given name, displays the plaintext once,
   * then refreshes the list.
   *
   * Args:
   *   e: Form submit event.
   */
  async function handleCreate(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    setCreating(true)
    setCreateError(null)
    try {
      const res = await createApiKey(newName.trim())
      setCreatedKey(res)
      setNewName('')
      await loadKeys()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create key.')
    } finally {
      setCreating(false)
    }
  }

  /**
   * Copies the plaintext key to the clipboard.
   *
   * Args:
   *   key: The plaintext API key string.
   */
  async function handleCopy(key: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard API unavailable (non-HTTPS or denied) — user can select + copy manually.
    }
  }

  /**
   * Revokes a key by its UUID and removes it from the list.
   *
   * Args:
   *   keyId: The UUID of the key to revoke.
   */
  async function handleRevoke(keyId: string): Promise<void> {
    setRevokingId(keyId)
    try {
      await revokeApiKey(keyId)
      setKeys(prev => prev.filter(k => k.id !== keyId))
    } catch {
      // Revoke failure is shown inline by re-enabling the button.
    } finally {
      setRevokingId(null)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="admin-section">
      <div className="admin-section-title">My API Keys</div>

      {/* Create form */}
      <form className="admin-create-row" onSubmit={(e) => { void handleCreate(e) }}>
        <input
          type="text"
          className="input admin-name-input"
          placeholder="Key name (e.g. automation-script)"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          required
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={creating || !newName.trim()}
        >
          {creating ? 'Creating...' : 'Create key'}
        </button>
      </form>
      {createError && <div className="error-banner">{createError}</div>}

      {/* One-time key reveal banner */}
      {createdKey && (
        <div className="admin-key-reveal">
          <div className="admin-key-reveal-header">
            <span className="admin-key-reveal-title">Key created — copy it now</span>
            <span className="admin-key-reveal-warn">
              You will NOT be able to see the plaintext key again after dismissing this.
            </span>
          </div>
          <div className="admin-key-reveal-body">
            <code className="admin-key-reveal-value">{createdKey.key}</code>
            <button
              type="button"
              className="btn btn-primary admin-copy-btn"
              onClick={() => { void handleCopy(createdKey.key) }}
            >
              {copied ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <button
            type="button"
            className="btn admin-key-reveal-dismiss"
            onClick={() => { setCreatedKey(null); setCopied(false) }}
          >
            I have saved it — dismiss
          </button>
        </div>
      )}

      {/* Key list */}
      {loadError && <div className="error-banner">{loadError}</div>}
      {keys.length === 0 && !loadError && (
        <p className="text-muted" style={{ marginTop: 12, fontSize: 13 }}>
          No active API keys yet.
        </p>
      )}
      {keys.map(k => (
        <div key={k.id} className="admin-key-row">
          <div className="admin-key-info">
            <span className="admin-key-name">{k.name}</span>
            <span className="admin-key-prefix text-muted">{k.prefix}...</span>
            <span className="text-dim" style={{ fontSize: 11 }}>
              Created {new Date(k.created_at).toLocaleDateString()}
              {k.last_used_at && (
                <> &middot; Last used {new Date(k.last_used_at).toLocaleDateString()}</>
              )}
            </span>
          </div>
          <button
            type="button"
            className="btn btn-danger"
            disabled={revokingId === k.id}
            onClick={() => { void handleRevoke(k.id) }}
          >
            {revokingId === k.id ? 'Revoking...' : 'Revoke'}
          </button>
        </div>
      ))}
    </div>
  )
}
