// ====== Code Summary ======
// ApiKeysList — DataTable of existing API keys with scope summary, dates, status,
// and revoke action.  Consumes ApiKeySummary[] (which now includes permissions).

import { useState } from 'react'
import type { ApiKeySummary, Collection } from '../../api/types'
import { revokeApiKey } from '../../api/client'
import { DataTable } from '../ui/primitives/DataTable'
import type { Column } from '../ui/primitives/DataTable'
import { Tag } from '../ui/primitives/Tag'
import { formatScopeSummary } from './apiKeyTypes'

// ── Types ────────────────────────────────────────────────────────────────────

interface ApiKeysListProps {
  /** Keys to display. */
  keys: ApiKeySummary[]
  /** All collections — used for scope summary display. */
  collections: Collection[]
  /** Called after a successful revoke so the parent can reload the list. */
  onRevoked: (keyId: string) => void
  /** Error from the list-fetch (shown above the table). */
  loadError: string | null
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: 'medium' })
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Dense table of API keys.
 *
 * Columns: Name, Scope, Created, Last used, Status, Revoke.
 * The Scope column uses formatScopeSummary (collection name resolution for
 * specific scopes).
 * Revoked keys show a greyed-out "Revoked" tag instead of the revoke button.
 *
 * Args:
 *   keys:      API key summaries to render.
 *   collections: Used to resolve collection names in scope summaries.
 *   onRevoked: Callback after a successful revoke.
 *   loadError: Error string shown above the table, or null.
 */
export function ApiKeysList({ keys, collections, onRevoked, loadError }: ApiKeysListProps) {
  const [revokingId, setRevokingId] = useState<string | null>(null)
  const [revokeErrors, setRevokeErrors] = useState<Record<string, string>>({})

  // Build a name-lookup map for scope summaries.
  const collectionName = (id: string): string | undefined =>
    collections.find(c => c.id === id)?.name

  /**
   * Revokes a key and reports back to the parent.
   *
   * Args:
   *   keyId: UUID of the key to revoke.
   */
  async function handleRevoke(keyId: string): Promise<void> {
    setRevokingId(keyId)
    setRevokeErrors(prev => { const n = { ...prev }; delete n[keyId]; return n })
    try {
      await revokeApiKey(keyId)
      onRevoked(keyId)
    } catch (err) {
      setRevokeErrors(prev => ({
        ...prev,
        [keyId]: err instanceof Error ? err.message : 'Revoke failed.',
      }))
    } finally {
      setRevokingId(null)
    }
  }

  const columns: Column<ApiKeySummary>[] = [
    {
      key: 'name',
      header: 'Name',
      render: k => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <span style={{ fontWeight: 500, color: 'var(--text)' }}>{k.name}</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-dim)' }}>
            {k.prefix}…
          </span>
        </div>
      ),
    },
    {
      key: 'scope',
      header: 'Scope',
      render: k => (
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {formatScopeSummary(k.permissions, collectionName)}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Created',
      render: k => (
        <span style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
          {formatDate(k.created_at)}
        </span>
      ),
    },
    {
      key: 'last_used_at',
      header: 'Last used',
      render: k => (
        <span style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
          {formatDate(k.last_used_at)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      align: 'center',
      render: k => k.revoked_at
        ? <Tag variant="error">revoked</Tag>
        : <Tag variant="done">active</Tag>,
    },
    {
      key: 'revoke',
      header: '',
      align: 'right',
      width: 90,
      render: k => {
        if (k.revoked_at) return null
        const isRevoking = revokingId === k.id
        const err = revokeErrors[k.id]
        return (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <button
              type="button"
              className="btn btn-danger"
              disabled={isRevoking}
              onClick={() => { void handleRevoke(k.id) }}
              style={{ fontSize: 11, padding: '2px 10px' }}
            >
              {isRevoking ? 'Revoking…' : 'Revoke'}
            </button>
            {err && (
              <span style={{ fontSize: 10, color: 'var(--s-error)', maxWidth: 120, textAlign: 'right' }}>
                {err}
              </span>
            )}
          </div>
        )
      },
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {loadError && (
        <div className="error-banner">{loadError}</div>
      )}
      <DataTable<ApiKeySummary>
        columns={columns}
        rows={keys}
        rowKey={k => k.id}
        emptyMessage="No API keys yet. Create one above."
        maxHeight="60vh"
      />
    </div>
  )
}
