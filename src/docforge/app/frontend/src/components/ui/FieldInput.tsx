import type { ParamSchema } from '../../api/types'

interface Props {
  schema: ParamSchema
  value: unknown
  onChange: (v: unknown) => void
  disabled?: boolean
  /**
   * When true, render the schema.description as a small hint below the label.
   * Defaults to false so existing uses (discovery forms, search filters) are
   * unaffected — only config-tree-driven panels opt in via RecursiveFieldRenderer.
   */
  showHint?: boolean
}

/**
 * Renders a single input for a ParamSchema descriptor.
 *
 * Covers: bool toggle, number (with bounds), string, secret, enum select.
 * When showHint is true and a description is available, it is shown as a
 * small hint beneath the label text (inside the label column).
 *
 * Args:
 *   schema:   ParamSchema descriptor from the discovery response.
 *   value:    Current value (may be undefined; falls back to schema.default).
 *   onChange: Called with the new value on every change.
 *   disabled: When true, the input is read-only.
 *   showHint: Show description as visible sub-text below the label (opt-in).
 */
export function FieldInput({ schema, value, onChange, disabled, showHint = false }: Props) {
  const { name, type, label, default: def, min, max, description, enum: opts } = schema
  const displayLabel = label || name
  const current = value ?? def

  // Hint span — only rendered when showHint=true and a description exists.
  const hint = showHint && description
    ? <span className="field-hint">{description}</span>
    : null

  if (opts && opts.length > 0) {
    return (
      <label className={`field-row${hint ? ' field-row-top' : ''}`}>
        <span className="field-label">
          {displayLabel}
          {hint}
        </span>
        <select
          className="input select"
          value={String(current ?? '')}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          title={description}
        >
          {opts.map(o => {
            const s = String(o)
            return <option key={s} value={s}>{s}</option>
          })}
        </select>
      </label>
    )
  }

  if (type === 'bool' || type === 'boolean') {
    return (
      <label className={`field-row field-toggle${hint ? ' field-row-top' : ''}`} title={description}>
        <span className="field-label">
          {displayLabel}
          {hint}
        </span>
        <button
          className={`toggle ${current ? 'toggle-on' : ''}`}
          onClick={() => onChange(!current)}
          disabled={disabled}
          type="button"
        >
          <span className="toggle-thumb" />
        </button>
      </label>
    )
  }

  if (type === 'int' || type === 'integer' || type === 'float' || type === 'number') {
    return (
      <label className={`field-row${hint ? ' field-row-top' : ''}`} title={description}>
        <span className="field-label">
          {displayLabel}
          {(min != null || max != null) && (
            <span className="field-bounds">{String(min ?? '−∞')} – {String(max ?? '∞')}</span>
          )}
          {hint}
        </span>
        <input
          className="input"
          type="number"
          value={(current as number | undefined) ?? ''}
          min={min as number | undefined}
          max={max as number | undefined}
          step={type === 'float' || type === 'number' ? 0.1 : 1}
          onChange={e => {
            const v = type === 'float' || type === 'number'
              ? parseFloat(e.target.value)
              : parseInt(e.target.value, 10)
            onChange(isNaN(v) ? undefined : v)
          }}
          disabled={disabled}
          style={{ width: 120 }}
        />
      </label>
    )
  }

  if (type === 'secret') {
    // Never pre-fill from a redacted sentinel — show empty with "already set" hint.
    const isRedacted = current === '•••'
    return (
      <label className={`field-row${hint ? ' field-row-top' : ''}`} title={description}>
        <span className="field-label">
          {displayLabel}
          {hint}
        </span>
        <input
          className="input mono"
          type="password"
          placeholder={isRedacted ? '(already set — leave blank to keep)' : description || '••••••••'}
          value={isRedacted ? '' : String(current ?? '')}
          onChange={e => onChange(e.target.value || undefined)}
          disabled={disabled}
        />
      </label>
    )
  }

  // Default: string input.
  return (
    <label className={`field-row${hint ? ' field-row-top' : ''}`} title={description}>
      <span className="field-label">
        {displayLabel}
        {hint}
      </span>
      <input
        className="input"
        type="text"
        value={String(current ?? '')}
        onChange={e => onChange(e.target.value || undefined)}
        disabled={disabled}
        placeholder={description}
      />
    </label>
  )
}
