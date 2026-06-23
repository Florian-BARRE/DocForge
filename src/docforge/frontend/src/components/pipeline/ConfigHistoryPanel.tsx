// ====== Code Summary ======
// Config version history panel for a collection.
// Fetches the version history on mount (and whenever the collection changes),
// lists every version newest-first, and lets the user restore a previous
// version via a rollback call. The most recent version is the current one and
// is therefore not restorable. After a successful rollback the parent is
// notified so it can reload the config state.

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getConfigHistory, rollbackConfig } from '../../api/client'
import type { ConfigVersionSummary } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConfigHistoryPanelProps {
  /** Collection whose config history is displayed. */
  collectionId: string
  /** Called after a successful rollback so the parent can reload configState. */
  onRolledBack: () => void
}

// ── Helpers ─────────────────────────────────────────────────────────────────────

/**
 * Format an ISO timestamp into a locale-aware, human-readable string.
 *
 * Args:
 *   iso: ISO 8601 date-time string from the backend.
 *
 * Returns:
 *   string: A readable local date-time, or the raw input if parsing fails.
 */
function formatDate(iso: string): string {
  const parsed = new Date(iso)
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString()
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * History panel listing every persisted config version with rollback actions.
 *
 * The list is rendered newest-first. The first (most recent) entry is the
 * current version: it is labelled "actuelle" and offers no restore button.
 * Every other version exposes a "Restaurer" button that re-applies it as a new
 * version, after which {@link ConfigHistoryPanelProps.onRolledBack} fires.
 *
 * Args:
 *   collectionId: Collection whose history is shown.
 *   onRolledBack: Callback invoked after a successful rollback.
 */
export function ConfigHistoryPanel({ collectionId, onRolledBack }: ConfigHistoryPanelProps) {
  const [versions, setVersions] = useState<ConfigVersionSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rollingBack, setRollingBack] = useState<number | null>(null)

  // 1. Load the history on mount and whenever the collection changes.
  const loadHistory = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await getConfigHistory(collectionId)
      // Newest-first ordering — sort defensively in case the API order changes.
      const sorted = [...resp.versions].sort((a, b) => b.version - a.version)
      setVersions(sorted)
    } catch {
      setError('Impossible de charger l’historique.')
    } finally {
      setLoading(false)
    }
  }, [collectionId])

  useEffect(() => {
    void loadHistory()
  }, [loadHistory])

  // 2. Restore a previous version, then notify the parent and refresh the list.
  async function handleRollback(version: number) {
    setRollingBack(version)
    setError(null)
    try {
      await rollbackConfig(collectionId, version)
      onRolledBack()
      await loadHistory()
    } catch {
      setError('Échec de la restauration.')
    } finally {
      setRollingBack(null)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loading) {
    return <div className="config-history-empty">Chargement de l’historique…</div>
  }

  if (versions.length === 0) {
    return <div className="config-history-empty">Aucun historique</div>
  }

  // The most recent version is the current one — first after newest-first sort.
  const currentVersion = versions[0]?.version

  return (
    <div className="config-history">
      {error && <div className="config-history-error">{error}</div>}
      {versions.map(v => {
        const isCurrent = v.version === currentVersion
        return (
          <div
            key={v.version}
            className={
              isCurrent ? 'config-history-row config-history-row-current' : 'config-history-row'
            }
          >
            <span className="config-history-ver">v{v.version}</span>
            <span className="mono">{v.pipeline_version}</span>
            <span className="config-history-note" title={v.note ?? undefined}>
              {v.note ?? '—'}
            </span>
            <span className="config-history-date">{formatDate(v.created_at)}</span>
            {isCurrent ? (
              <span className="tag">actuelle</span>
            ) : (
              <button
                type="button"
                className="btn btn-ghost"
                disabled={rollingBack !== null}
                onClick={() => { void handleRollback(v.version) }}
              >
                {rollingBack === v.version ? 'Restauration…' : 'Restaurer'}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
