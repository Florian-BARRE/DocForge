// ====== Code Summary ======
// ApiKeysPage — the root-only page for managing permissioned API keys.
//
// Rendered when the "API Keys" NavRail entry is active (root only).
// Composes three sections:
//   1. CreateKeyForm — name + permission builder + submit.
//   2. KeyRevealCallout — one-time plaintext reveal after creation.
//   3. ApiKeysList — DataTable of all keys with revoke action.
//
// Collections are fetched once on mount and passed down so child components
// can resolve collection names without additional fetches.

import { useEffect, useState } from 'react'
import type { ApiKeyCreatedResponse, ApiKeySummary, Collection } from '../../api/types'
import { listApiKeys, listCollections } from '../../api/client'
import { SectionHeader } from '../ui/primitives/SectionHeader'
import { Spinner } from '../ui/primitives/Spinner'
import { CreateKeyForm } from './CreateKeyForm'
import { KeyRevealCallout } from './KeyRevealCallout'
import { ApiKeysList } from './ApiKeysList'

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Full-page API key management view (root only).
 *
 * State management:
 *   - `keys`        — the fetched list of ApiKeySummary records.
 *   - `collections` — for collection name resolution in scope summaries.
 *   - `createdKey`  — the most recently created key, shown once then cleared.
 *   - `loadError`   — any error from the initial list fetch.
 *   - `loading`     — true while the initial data load is in flight.
 */
export function ApiKeysPage() {
  const [keys, setKeys]               = useState<ApiKeySummary[]>([])
  const [collections, setCollections] = useState<Collection[]>([])
  const [loadError, setLoadError]     = useState<string | null>(null)
  const [loading, setLoading]         = useState(true)
  // The one-time plaintext reveal after key creation.
  const [createdKey, setCreatedKey]   = useState<ApiKeyCreatedResponse | null>(null)

  // 1. Load keys and collections on mount.
  useEffect(() => {
    void load()
  }, [])

  async function load(): Promise<void> {
    setLoading(true)
    setLoadError(null)
    try {
      const [keysRes, colsRes] = await Promise.all([
        listApiKeys(),
        listCollections(),
      ])
      setKeys(keysRes.keys)
      setCollections(colsRes.collections)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load data.')
    } finally {
      setLoading(false)
    }
  }

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Called by CreateKeyForm on success.
   * Displays the one-time reveal callout and appends the key to the list.
   *
   * Args:
   *   created: The full creation response (includes plaintext key).
   */
  function handleCreated(created: ApiKeyCreatedResponse): void {
    setCreatedKey(created)
    // Append to the list immediately so it appears without a full reload.
    const summary: ApiKeySummary = {
      id: created.id,
      name: created.name,
      prefix: created.prefix,
      created_at: created.created_at,
      last_used_at: null,
      revoked_at: null,
      permissions: created.permissions,
    }
    setKeys(prev => [summary, ...prev])
  }

  /**
   * Called by ApiKeysList after a successful revoke.
   * Marks the key as revoked in-place to avoid a full reload.
   *
   * Args:
   *   keyId: UUID of the revoked key.
   */
  function handleRevoked(keyId: string): void {
    const now = new Date().toISOString()
    setKeys(prev => prev.map(k => k.id === keyId ? { ...k, revoked_at: now } : k))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Spinner size={20} />
      </div>
    )
  }

  return (
    <div style={{
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 24,
      maxWidth: 760,
    }}>
      {/* ── Create section ── */}
      <section>
        <SectionHeader gap={12}>Create API Key</SectionHeader>
        <CreateKeyForm collections={collections} onCreated={handleCreated} />
      </section>

      {/* ── One-time reveal callout ── */}
      {createdKey && (
        <KeyRevealCallout
          created={createdKey}
          onDismiss={() => setCreatedKey(null)}
        />
      )}

      {/* ── Keys list ── */}
      <section>
        <SectionHeader gap={10}>Existing Keys</SectionHeader>
        <ApiKeysList
          keys={keys}
          collections={collections}
          onRevoked={handleRevoked}
          loadError={loadError}
        />
      </section>
    </div>
  )
}
