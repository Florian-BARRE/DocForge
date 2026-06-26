// ====== Code Summary ======
// CreateKeyForm — form for creating a new API key.
// Composes a name input + PermissionBuilder, then calls createApiKey on submit.
// Emits the created key to the parent via onCreated so the plaintext reveal
// callout can be shown exactly once.

import { useState, useCallback, type FormEvent } from 'react'
import type { Collection, Permissions, ApiKeyCreatedResponse } from '../../api/types'
import { createApiKey } from '../../api/client'
import { PermissionBuilder } from './PermissionBuilder'

// ── Types ────────────────────────────────────────────────────────────────────

interface CreateKeyFormProps {
  /** Available collections for the permission builder. */
  collections: Collection[]
  /** Called with the full creation response on success. */
  onCreated: (key: ApiKeyCreatedResponse) => void
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Form for creating a new permissioned API key.
 *
 * Sections:
 *   1. Name input — human-readable label for the key.
 *   2. PermissionBuilder — scope selection (all-collections vs specific + roles).
 *   3. Submit button + inline error display.
 *
 * On success, the parent is notified via onCreated and the form resets.
 *
 * Args:
 *   collections: Used by PermissionBuilder to populate the collection selector.
 *   onCreated:   Called with the ApiKeyCreatedResponse on successful creation.
 */
export function CreateKeyForm({ collections, onCreated }: CreateKeyFormProps) {
  const [name, setName]               = useState('')
  const [permissions, setPermissions] = useState<Permissions>({
    entries: [{ collection_id: '*', role: 'admin' }],
  })
  const [submitting, setSubmitting]   = useState(false)
  const [error, setError]             = useState<string | null>(null)

  // Stable reference for PermissionBuilder's onChange to avoid re-renders.
  const handlePermissionsChange = useCallback((p: Permissions) => {
    setPermissions(p)
  }, [])

  /**
   * Submits the form — calls createApiKey and reports the result.
   *
   * Args:
   *   e: The form submission event.
   */
  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) return

    // Guard: require at least one scope entry with a collection selected.
    const validEntries = permissions.entries.filter(en => en.collection_id !== '')
    if (validEntries.length === 0) {
      setError('Add at least one permission scope before creating the key.')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      const created = await createApiKey(trimmedName, {
        entries: validEntries,
      })
      // 1. Reset form state.
      setName('')
      setPermissions({ entries: [{ collection_id: '*', role: 'admin' }] })
      // 2. Notify parent so it can display the one-time reveal callout.
      onCreated(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create API key.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={(e) => { void handleSubmit(e) }}
      style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
    >
      {/* ── Name ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <label style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Key name
        </label>
        <input
          type="text"
          className="input"
          placeholder="e.g. ci-pipeline, mcp-server"
          value={name}
          disabled={submitting}
          onChange={e => setName(e.target.value)}
          required
          style={{ fontSize: 13 }}
        />
      </div>

      {/* ── Permissions ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Permissions
        </div>
        <PermissionBuilder
          onChange={handlePermissionsChange}
          collections={collections}
          disabled={submitting}
        />
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="error-banner">{error}</div>
      )}

      {/* ── Submit ── */}
      <button
        type="submit"
        className="btn btn-primary"
        disabled={submitting || !name.trim()}
        style={{ alignSelf: 'flex-start', padding: '6px 16px' }}
      >
        {submitting ? 'Creating…' : 'Create key'}
      </button>
    </form>
  )
}
