import type { ParamSchema } from '../../api/types'

interface Props {
  schema: ParamSchema
  value: unknown
  onChange: (v: unknown) => void
  disabled?: boolean
}

/**
 * Renders a single input for a ParamSchema descriptor.
 * Covers: bool toggle, number (with bounds), string, secret, enum select.
 */
export function FieldInput({ schema, value, onChange, disabled }: Props) {
  const { name, type, label, default: def, min, max, description, enum: opts } = schema
  const displayLabel = label || name
  const current = value ?? def

  if (opts && opts.length > 0) {
    return (
      <label className="field-row">
        <span className="field-label">{displayLabel}</span>
        <select
          className="input select"
          value={String(current ?? '')}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          title={description}
        >
          {opts.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      </label>
    )
  }

  if (type === 'bool' || type === 'boolean') {
    return (
      <label className="field-row field-toggle" title={description}>
        <span className="field-label">{displayLabel}</span>
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
      <label className="field-row" title={description}>
        <span className="field-label">
          {displayLabel}
          {(min != null || max != null) && (
            <span className="field-bounds">{min ?? '−∞'} – {max ?? '∞'}</span>
          )}
        </span>
        <input
          className="input"
          type="number"
          value={current as number ?? ''}
          min={min ?? undefined}
          max={max ?? undefined}
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
      <label className="field-row" title={description}>
        <span className="field-label">{displayLabel}</span>
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

  // Default: string input
  return (
    <label className="field-row" title={description}>
      <span className="field-label">{displayLabel}</span>
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
