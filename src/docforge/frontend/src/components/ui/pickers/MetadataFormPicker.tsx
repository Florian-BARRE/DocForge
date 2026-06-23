// ====== Code Summary ======
// MetadataFormPicker — kind="map" + capability="metadata_write" form editor.
// One typed input per custom field, with type badge and required/optional
// indicator.  Produces { field_name: value } (no operator — raw metadata object
// for ingest).  MetaFieldInput is the locally-scoped typed input wrapper.

// ====== Internal Project Imports ======
import type { DynamicField, ParamSchema } from '../../../api/types'

// ====== Local Project Imports ======
import { labelFromPath } from './pickerHelpers'

// Thin wrapper around FieldInput that handles enum → select and bool → toggle inline.
function MetaFieldInput({
  schema, value, onChange, required,
}: {
  schema: ParamSchema
  value: unknown
  onChange: (v: unknown) => void
  required: boolean
}) {
  // Enum field — native select with empty first option if optional
  if (schema.enum && schema.enum.length > 0) {
    return (
      <select
        className="input select"
        value={String(value ?? '')}
        onChange={e => onChange(e.target.value || undefined)}
        style={{ flex: 1 }}
      >
        {!required && <option value="">—</option>}
        {schema.enum.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    )
  }

  // Bool field
  if (schema.type === 'bool' || schema.type === 'boolean') {
    const checked = Boolean(value ?? false)
    return (
      <button
        className={`toggle ${checked ? 'toggle-on' : ''}`}
        onClick={() => onChange(!checked)}
        type="button"
        style={{ flex: 'none' }}
      >
        <span className="toggle-thumb" />
      </button>
    )
  }

  // Number field
  if (schema.type === 'int' || schema.type === 'integer' || schema.type === 'float' || schema.type === 'number') {
    return (
      <input
        className="input"
        type="number"
        value={value !== undefined && value !== null ? String(value) : ''}
        min={schema.min ?? undefined}
        max={schema.max ?? undefined}
        step={schema.type === 'float' || schema.type === 'number' ? 0.1 : 1}
        onChange={e => {
          const n = schema.type === 'float' || schema.type === 'number'
            ? parseFloat(e.target.value)
            : parseInt(e.target.value, 10)
          onChange(isNaN(n) ? undefined : n)
        }}
        placeholder={required ? schema.name : `${schema.name} (optional)`}
        style={{ flex: 1 }}
      />
    )
  }

  // Default: string
  return (
    <input
      className="input"
      type="text"
      value={String(value ?? '')}
      onChange={e => onChange(e.target.value || undefined)}
      placeholder={required ? schema.name : `${schema.name} (optional)`}
      style={{ flex: 1 }}
    />
  )
}

/**
 * Typed metadata form for kind="map" fields with capability="metadata_write".
 *
 * Renders one typed input per custom field with a type badge and a
 * required/optional indicator.  Empty values are removed from the object.
 *
 * Args:
 *   field:    Dynamic field descriptor (capability="metadata_write").
 *   value:    Current metadata object.
 *   onChange: Callback to publish the updated metadata object.
 *   label:    Optional override label.
 */
export function MetadataFormPicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: Record<string, unknown> | undefined
  onChange: (v: Record<string, unknown>) => void
  label?: string
}) {
  const current = value ?? {}

  function set(fieldId: string, v: unknown) {
    const next = { ...current }
    if (v === undefined || v === '' || v === null) {
      delete next[fieldId]
    } else {
      next[fieldId] = v
    }
    onChange(next)
  }

  if (field.choices.length === 0) {
    return (
      <div className="picker">
        <div className="picker-label">{label || labelFromPath(field.field_path)}</div>
        <div className="picker-unresolved text-muted" style={{ fontSize: 12 }}>
          No custom metadata fields defined on this collection.
        </div>
      </div>
    )
  }

  return (
    <div className="picker">
      <div className="picker-label">{label || labelFromPath(field.field_path)}</div>
      <div className="meta-form">
        {field.choices.map(c => {
          const valueSchema = c.fields[0]
          const isRequired = c.note === 'required'
          return (
            <div key={c.id} className="meta-form-row">
              <div className="meta-form-label">
                <span className="meta-field-name mono">{c.label || c.id}</span>
                <span className={`tag ${isRequired ? 'tag-running' : ''}`} style={{ fontSize: 10 }}>
                  {isRequired ? 'required' : 'optional'}
                </span>
                {valueSchema && (
                  <span className="tag" style={{ fontSize: 10, marginLeft: 4 }}>
                    {valueSchema.type}
                  </span>
                )}
              </div>
              {valueSchema ? (
                <MetaFieldInput
                  schema={valueSchema}
                  value={current[c.id]}
                  onChange={v => set(c.id, v)}
                  required={isRequired}
                />
              ) : (
                <input
                  className="input"
                  type="text"
                  value={String(current[c.id] ?? '')}
                  onChange={e => set(c.id, e.target.value || undefined)}
                  placeholder={c.id}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
