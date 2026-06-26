// ====== Code Summary ======
// SegmentedControl — a compact button-group that presents a small set of
// mutually exclusive options.  Used in the Search Lab for vector mode and
// fusion selection.  Purely presentational; all state is managed by the caller.

// ── Types ─────────────────────────────────────────────────────────────────────

interface Option<T extends string> {
  /** Unique value for this option (becomes the controlled value). */
  value: T
  /** Short human-readable label displayed in the button. */
  label: string
}

interface SegmentedControlProps<T extends string> {
  /** The available options to render. */
  options: Option<T>[]
  /** Currently active value. */
  value: T
  /** Called when the user selects a different option. */
  onChange: (value: T) => void
  /** When true, all buttons are non-interactive. */
  disabled?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Segmented control — an inline button group for a closed set of options.
 *
 * Renders as a single bordered pill split into N buttons; the active option
 * gets a filled background.  Uses `.segmented-control` / `.segmented-btn` /
 * `.segmented-btn-active` CSS classes from global.css.
 *
 * Args:
 *   options:  List of {value, label} pairs to render.
 *   value:    Currently selected value.
 *   onChange: Called with the new value when a button is clicked.
 *   disabled: Disables all buttons when true.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  disabled = false,
}: SegmentedControlProps<T>) {
  return (
    <div className="segmented-control" role="group">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          className={`segmented-btn${value === opt.value ? ' segmented-btn-active' : ''}`}
          onClick={() => !disabled && onChange(opt.value)}
          disabled={disabled}
          aria-pressed={value === opt.value}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
