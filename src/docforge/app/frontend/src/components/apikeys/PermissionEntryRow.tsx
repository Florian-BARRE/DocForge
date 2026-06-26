// ====== Code Summary ======
// PermissionEntryRow — one row in the "specific collections" permission builder.
// Shows a collection selector, a role chip group (read/write/admin), an
// "Advanced" toggle that expands capability checkboxes, and a remove button.

import type { Collection } from '../../api/types'
import type { PermissionRole } from '../../api/types'
import type { PermissionRowDraft } from './apiKeyTypes'
import { ROLE_CAPABILITIES } from './apiKeyTypes'
import { RoleChipGroup } from './RoleChipGroup'
import { CapabilityCheckboxes } from './CapabilityCheckboxes'

// ── Types ────────────────────────────────────────────────────────────────────

interface PermissionEntryRowProps {
  /** The draft state for this row. */
  draft: PermissionRowDraft
  /** All available collections for the dropdown. */
  collections: Collection[]
  /** Called when any field in the row changes. */
  onChange: (updated: PermissionRowDraft) => void
  /** Called when the user clicks the remove button. */
  onRemove: () => void
  /** Disable all controls while submitting. */
  disabled?: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * One scoped permission entry row for the permission builder.
 *
 * Three interactive regions:
 *   1. Collection <select> — choose which collection this entry targets.
 *   2. Role chip group (read / write / admin) — shortcut role.
 *   3. Advanced toggle — expands CapabilityCheckboxes, sets role to 'custom'.
 *
 * Args:
 *   draft:       Current row state.
 *   collections: Available collections for the selector.
 *   onChange:    Fires with a full updated draft on any change.
 *   onRemove:    Fires when the remove button is clicked.
 *   disabled:    When true, all controls are inactive.
 */
export function PermissionEntryRow({
  draft,
  collections,
  onChange,
  onRemove,
  disabled = false,
}: PermissionEntryRowProps) {
  /**
   * Switches the role to a shortcut and closes the advanced panel.
   *
   * Args:
   *   role: The new shortcut role.
   */
  function handleRoleChange(role: Exclude<PermissionRole, 'custom'>): void {
    onChange({ ...draft, role, capabilities: ROLE_CAPABILITIES[role], advancedOpen: false })
  }

  /**
   * Toggles the advanced capability panel.
   * Opening it switches the role to 'custom' and pre-fills with current expansion.
   */
  function handleAdvancedToggle(): void {
    if (!draft.advancedOpen) {
      // 1. Entering advanced mode: seed capabilities from the current shortcut role
      //    if no custom capabilities are set yet.
      const seedCaps = draft.role !== 'custom'
        ? ROLE_CAPABILITIES[draft.role as Exclude<PermissionRole, 'custom'>]
        : draft.capabilities
      onChange({ ...draft, role: 'custom', capabilities: seedCaps, advancedOpen: true })
    } else {
      // 2. Closing advanced mode: fall back to the nearest fitting shortcut role
      //    based on the selected capabilities, or keep 'custom' if no shortcut matches.
      const cap = new Set(draft.capabilities)
      const matchedRole: Exclude<PermissionRole, 'custom'> | null =
        cap.size === ROLE_CAPABILITIES.read.length &&
        ROLE_CAPABILITIES.read.every(c => cap.has(c)) &&
        ROLE_CAPABILITIES.read.length === cap.size
          ? 'read'
          : cap.size === ROLE_CAPABILITIES.write.length &&
            ROLE_CAPABILITIES.write.every(c => cap.has(c))
            ? 'write'
            : cap.size === ROLE_CAPABILITIES.admin.length &&
              ROLE_CAPABILITIES.admin.every(c => cap.has(c))
              ? 'admin'
              : null
      onChange({
        ...draft,
        role: matchedRole ?? 'custom',
        advancedOpen: false,
      })
    }
  }

  const isCustom = draft.role === 'custom'
  const roleForChips: Exclude<PermissionRole, 'custom'> =
    isCustom ? 'read' : (draft.role as Exclude<PermissionRole, 'custom'>)

  return (
    <div style={{
      background: 'var(--surface-raised)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '8px 10px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      {/* ── Row: collection + role chips + advanced + remove ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {/* Collection selector */}
        <select
          className="input select"
          value={draft.collectionId}
          disabled={disabled}
          onChange={e => onChange({ ...draft, collectionId: e.target.value })}
          style={{ flex: '1 1 160px', minWidth: 120, fontSize: 12 }}
        >
          <option value="">Select collection…</option>
          {collections.map(c => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        {/* Role chips — dimmed when in custom mode */}
        <div style={{ opacity: isCustom ? 0.4 : 1, pointerEvents: isCustom ? 'none' : 'auto' }}>
          <RoleChipGroup
            value={roleForChips}
            onChange={handleRoleChange}
            disabled={disabled}
          />
        </div>

        {/* Advanced toggle */}
        <button
          type="button"
          onClick={handleAdvancedToggle}
          disabled={disabled}
          style={{
            padding: '3px 8px',
            fontSize: 11,
            fontFamily: 'var(--font-ui)',
            borderRadius: 'var(--radius-sm)',
            border: `1px solid ${draft.advancedOpen ? 'var(--accent)' : 'var(--border)'}`,
            background: draft.advancedOpen ? 'var(--accent-soft)' : 'transparent',
            color: draft.advancedOpen ? 'var(--accent)' : 'var(--text-dim)',
            cursor: disabled ? 'default' : 'pointer',
          }}
        >
          {draft.advancedOpen ? 'Advanced ▲' : 'Advanced ▼'}
        </button>

        {/* Remove row */}
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          title="Remove this scope"
          style={{
            padding: '3px 7px',
            fontSize: 12,
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            background: 'transparent',
            color: 'var(--text-dim)',
            cursor: disabled ? 'default' : 'pointer',
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </div>

      {/* ── Expanded capabilities panel ── */}
      {draft.advancedOpen && (
        <div style={{
          borderTop: '1px solid var(--border)',
          paddingTop: 6,
        }}>
          <div style={{ fontSize: 10, color: 'var(--text-dim)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Fine-grained capabilities
          </div>
          <CapabilityCheckboxes
            value={draft.capabilities}
            onChange={caps => onChange({ ...draft, capabilities: caps })}
            disabled={disabled}
          />
        </div>
      )}
    </div>
  )
}
