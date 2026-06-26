// ====== Code Summary ======
// PermissionBuilder — the permission scope builder for API key creation.
//
// Two modes:
//   "All collections"  — one implicit entry with collection_id: '*' + a role chip group.
//   "Specific"         — user-defined list of entries, each via PermissionEntryRow.
//
// Outputs a Permissions object whenever the internal draft changes via onChange.

import { useState, useEffect, useCallback } from 'react'
import type { Collection, Permissions, PermissionRole } from '../../api/types'
import type { PermissionRowDraft } from './apiKeyTypes'
import { ROLE_CAPABILITIES } from './apiKeyTypes'
import { RoleChipGroup } from './RoleChipGroup'
import { PermissionEntryRow } from './PermissionEntryRow'

// ── Types ────────────────────────────────────────────────────────────────────

interface PermissionBuilderProps {
  /** Called whenever the built permissions change. */
  onChange: (permissions: Permissions) => void
  /** All available collections (for the per-collection selectors). */
  collections: Collection[]
  /** Disable all controls while the parent form is submitting. */
  disabled?: boolean
}

type ScopeMode = 'all' | 'specific'

// ── Counter for stable local IDs ──────────────────────────────────────────────

let _rowIdCounter = 0
function nextLocalId(): string {
  return `row-${++_rowIdCounter}`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Converts the internal draft state into the Permissions wire shape.
 *
 * Args:
 *   mode: 'all' — one wildcard entry; 'specific' — one entry per row.
 *   allRole: Role for the all-collections entry (only used when mode='all').
 *   rows: Draft rows (only used when mode='specific').
 *
 * Returns:
 *   Permissions object ready to send to the backend.
 */
function buildPermissions(
  mode: ScopeMode,
  allRole: Exclude<PermissionRole, 'custom'>,
  rows: PermissionRowDraft[],
): Permissions {
  if (mode === 'all') {
    return {
      entries: [{
        collection_id: '*',
        role: allRole,
        capabilities: ROLE_CAPABILITIES[allRole],
      }],
    }
  }

  // Filter out empty rows (no collection selected yet).
  const valid = rows.filter(r => r.collectionId !== '')
  return {
    entries: valid.map(r => ({
      collection_id: r.collectionId,
      role: r.role,
      ...(r.role === 'custom' ? { capabilities: r.capabilities } : {}),
    })),
  }
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Permission scope builder for new API keys.
 *
 * Renders a mode toggle (All / Specific) then the appropriate controls.
 * Calls onChange on every state mutation so the parent always has the latest
 * Permissions payload.
 *
 * Args:
 *   onChange:    Receives the current Permissions value on every change.
 *   collections: Available collections for specific-scope rows.
 *   disabled:    Freeze controls while the parent form is submitting.
 */
export function PermissionBuilder({ onChange, collections, disabled = false }: PermissionBuilderProps) {
  const [mode, setMode]         = useState<ScopeMode>('all')
  const [allRole, setAllRole]   = useState<Exclude<PermissionRole, 'custom'>>('admin')
  const [rows, setRows]         = useState<PermissionRowDraft[]>([])

  // Emit updated Permissions whenever draft state changes.
  const emit = useCallback(
    (m: ScopeMode, r: Exclude<PermissionRole, 'custom'>, rs: PermissionRowDraft[]) => {
      onChange(buildPermissions(m, r, rs))
    },
    [onChange],
  )

  useEffect(() => {
    emit(mode, allRole, rows)
  // emit is stable (useCallback); mode/allRole/rows are the real dependencies.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, allRole, rows])

  // ── Handlers ──────────────────────────────────────────────────────────────

  /**
   * Switches the scope mode and initialises rows when entering specific mode.
   *
   * Args:
   *   next: The new scope mode.
   */
  function handleModeChange(next: ScopeMode): void {
    if (next === 'specific' && rows.length === 0) {
      // Start with one blank row.
      setRows([{
        localId: nextLocalId(),
        collectionId: '',
        role: 'read',
        capabilities: ROLE_CAPABILITIES.read,
        advancedOpen: false,
      }])
    }
    setMode(next)
  }

  /**
   * Adds a blank specific-scope row.
   */
  function handleAddRow(): void {
    setRows(prev => [...prev, {
      localId: nextLocalId(),
      collectionId: '',
      role: 'read',
      capabilities: ROLE_CAPABILITIES.read,
      advancedOpen: false,
    }])
  }

  /**
   * Updates a specific row by its local ID.
   *
   * Args:
   *   localId: The row's stable local key.
   *   updated: The new draft state for that row.
   */
  function handleRowChange(localId: string, updated: PermissionRowDraft): void {
    setRows(prev => prev.map(r => r.localId === localId ? updated : r))
  }

  /**
   * Removes a specific row by its local ID.
   *
   * Args:
   *   localId: The row to remove.
   */
  function handleRowRemove(localId: string): void {
    setRows(prev => prev.filter(r => r.localId !== localId))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* ── Mode toggle ── */}
      <div style={{ display: 'flex', gap: 0 }}>
        {(['all', 'specific'] as ScopeMode[]).map(m => {
          const isActive = mode === m
          return (
            <button
              key={m}
              type="button"
              disabled={disabled}
              onClick={() => handleModeChange(m)}
              style={{
                padding: '4px 14px',
                fontSize: 12,
                fontFamily: 'var(--font-ui)',
                fontWeight: isActive ? 600 : 400,
                border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
                borderRadius: m === 'all' ? 'var(--radius-sm) 0 0 var(--radius-sm)' : '0 var(--radius-sm) var(--radius-sm) 0',
                background: isActive ? 'var(--accent-soft)' : 'var(--surface-raised)',
                color: isActive ? 'var(--accent)' : 'var(--text-muted)',
                cursor: disabled ? 'default' : 'pointer',
                transition: 'background 0.1s, border-color 0.1s',
              }}
            >
              {m === 'all' ? 'All collections' : 'Specific collections'}
            </button>
          )
        })}
      </div>

      {/* ── All-collections mode: single role chip group ── */}
      {mode === 'all' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Role:</span>
          <RoleChipGroup value={allRole} onChange={r => setAllRole(r)} disabled={disabled} />
        </div>
      )}

      {/* ── Specific mode: list of entry rows ── */}
      {mode === 'specific' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {rows.length === 0 && (
            <p style={{ fontSize: 12, color: 'var(--text-dim)', margin: 0 }}>
              No scopes added. Click "Add scope" to add one.
            </p>
          )}
          {rows.map(row => (
            <PermissionEntryRow
              key={row.localId}
              draft={row}
              collections={collections}
              onChange={updated => handleRowChange(row.localId, updated)}
              onRemove={() => handleRowRemove(row.localId)}
              disabled={disabled}
            />
          ))}
          <button
            type="button"
            disabled={disabled}
            onClick={handleAddRow}
            style={{
              alignSelf: 'flex-start',
              padding: '4px 12px',
              fontSize: 12,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--surface-raised)',
              color: 'var(--text-muted)',
              cursor: disabled ? 'default' : 'pointer',
            }}
          >
            + Add scope
          </button>
        </div>
      )}
    </div>
  )
}
