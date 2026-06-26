// ====== Code Summary ======
// CapabilityCheckboxes — fine-grained capability picker shown when the user
// expands "Advanced" on a permission entry row.  Renders one checkbox per
// capability with a human-readable label.  All colors from CSS vars.

import type { Capability } from '../../api/types'
import { ALL_CAPABILITIES, CAPABILITY_LABELS } from './apiKeyTypes'

// ── Types ────────────────────────────────────────────────────────────────────

interface CapabilityCheckboxesProps {
  /** Currently checked capabilities. */
  value: Capability[]
  /** Called whenever the selection changes. */
  onChange: (capabilities: Capability[]) => void
  /** Optional: disable all checkboxes while submitting. */
  disabled?: boolean
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Checkbox grid for fine-grained capability selection.
 *
 * Renders one checkbox per capability in a two-column layout.  Checking or
 * unchecking a box fires onChange with the updated list.
 *
 * Args:
 *   value:    Currently selected capabilities.
 *   onChange: Callback with the full updated list.
 *   disabled: When true, all checkboxes are non-interactive.
 */
export function CapabilityCheckboxes({ value, onChange, disabled = false }: CapabilityCheckboxesProps) {
  /**
   * Toggles a single capability in or out of the selection list.
   *
   * Args:
   *   cap: The capability to toggle.
   */
  function toggle(cap: Capability): void {
    const next = value.includes(cap)
      ? value.filter(c => c !== cap)
      : [...value, cap]
    onChange(next)
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '4px 16px',
      padding: '8px 0',
    }}>
      {ALL_CAPABILITIES.map(cap => (
        <label
          key={cap}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 11,
            color: 'var(--text-muted)',
            cursor: disabled ? 'default' : 'pointer',
            userSelect: 'none',
          }}
        >
          <input
            type="checkbox"
            checked={value.includes(cap)}
            disabled={disabled}
            onChange={() => toggle(cap)}
            style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          {CAPABILITY_LABELS[cap]}
        </label>
      ))}
    </div>
  )
}
