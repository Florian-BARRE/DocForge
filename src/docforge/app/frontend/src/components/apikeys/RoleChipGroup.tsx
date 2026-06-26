// ====== Code Summary ======
// RoleChipGroup — a three-chip selector for read / write / admin role shortcuts.
// The active chip uses accent-soft styling; inactive chips are muted surface.
// All colors come from CSS vars (token-driven).

import type { PermissionRole } from '../../api/types'

// ── Types ────────────────────────────────────────────────────────────────────

interface RoleChipGroupProps {
  /** Currently selected role shortcut (not 'custom' — custom uses CapabilityCheckboxes). */
  value: Exclude<PermissionRole, 'custom'>
  /** Called when the user clicks a chip. */
  onChange: (role: Exclude<PermissionRole, 'custom'>) => void
  /** Optional: disable all chips (e.g. while submitting). */
  disabled?: boolean
}

const ROLES: { key: Exclude<PermissionRole, 'custom'>; label: string; title: string }[] = [
  { key: 'read',  label: 'read',  title: 'Read: documents.read, search, config.read'         },
  { key: 'write', label: 'write', title: 'Write: read + documents.write, config.write, chunks.write' },
  { key: 'admin', label: 'admin', title: 'Admin: write + collection.admin'                   },
]

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Chip-style toggle group for read / write / admin role shortcuts.
 *
 * One chip is always selected.  Clicking a chip fires onChange with the new
 * role.  The component is controlled — value must come from the parent.
 *
 * Args:
 *   value:    The currently active role.
 *   onChange: Callback fired when a chip is clicked.
 *   disabled: When true, all chips are non-interactive.
 */
export function RoleChipGroup({ value, onChange, disabled = false }: RoleChipGroupProps) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {ROLES.map(r => {
        const isActive = r.key === value
        return (
          <button
            key={r.key}
            type="button"
            title={r.title}
            disabled={disabled}
            onClick={() => onChange(r.key)}
            style={{
              padding: '3px 10px',
              fontSize: 11,
              fontFamily: 'var(--font-ui)',
              fontWeight: isActive ? 600 : 400,
              borderRadius: 'var(--radius-sm)',
              border: `1px solid ${isActive ? 'color-mix(in srgb, var(--accent) 50%, transparent)' : 'var(--border)'}`,
              background: isActive ? 'var(--accent-soft)' : 'var(--surface-raised)',
              color: isActive ? 'var(--accent)' : 'var(--text-muted)',
              cursor: disabled ? 'default' : 'pointer',
              transition: 'background 0.1s, border-color 0.1s, color 0.1s',
              userSelect: 'none',
            }}
          >
            {r.label}
          </button>
        )
      })}
    </div>
  )
}
