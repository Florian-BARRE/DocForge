// ====== Code Summary ======
// Toggle (switch) primitive — wraps the existing .toggle CSS class.
// Used for boolean config fields (enabled/disabled stages, flags).

// ── Types ────────────────────────────────────────────────────────────────────

interface ToggleProps {
  /** Current boolean value. */
  checked: boolean
  /** Called when the user clicks the toggle. */
  onChange: (checked: boolean) => void
  /** Whether the toggle is interactive. Defaults to true. */
  disabled?: boolean
  /** Accessible label. */
  title?: string
  className?: string
}

// ── Component ────────────────────────────────────────────────────────────────

/**
 * Binary switch (on/off toggle).
 *
 * Uses `.toggle` / `.toggle-on` from global.css, which reads all colors
 * from CSS vars (token-driven). The thumb slides on/off.
 *
 * Args:
 *   checked: Current state.
 *   onChange: Callback receiving the new boolean state.
 *   disabled: Prevents interaction when true.
 *   title: Tooltip / accessible label.
 */
export function Toggle({ checked, onChange, disabled = false, title, className = '' }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      disabled={disabled}
      className={`toggle${checked ? ' toggle-on' : ''} ${className}`.trim()}
      onClick={() => !disabled && onChange(!checked)}
      style={{ opacity: disabled ? 0.45 : 1 }}
    >
      <span className="toggle-thumb" />
    </button>
  )
}
