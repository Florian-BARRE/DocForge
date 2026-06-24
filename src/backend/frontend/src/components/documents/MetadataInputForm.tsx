// ====== Code Summary ======
// Inline form that collects metadata key-values before a document is ingested.
// Driven entirely by the collection's metadata_fields schema: one input per
// user-defined field, typed appropriately (text, number, date, checkbox, select).
// Required fields are flagged. Values are passed back via onChange so the parent
// can include them in the ingestDocument call.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { MetaField } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface MetadataInputFormProps {
  /** User-defined metadata fields for this collection (system fields excluded). */
  fields: MetaField[]
  /** Called on every change with the current values map. */
  onChange: (values: Record<string, unknown>) => void
  /** Whether the form should be shown (controlled by parent). */
  isOpen: boolean
  /** Toggle expand/collapse. */
  onToggle: () => void
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Returns the HTML input type that best matches a metadata field type.
 *
 * Args:
 *   fieldType: The field_type string from the MetaField schema.
 *
 * Returns:
 *   A suitable HTML input type string.
 */
function inputTypeFor(fieldType: string): string {
  switch (fieldType) {
    case 'integer':
    case 'float':
      return 'number'
    case 'boolean':
      return 'checkbox'
    case 'date':
      return 'date'
    default:
      return 'text'
  }
}

/**
 * Casts a raw string input value to the appropriate JS type for the field.
 *
 * Args:
 *   raw:       Raw string value from the input element.
 *   fieldType: The field_type string from the MetaField schema.
 *
 * Returns:
 *   Appropriately typed value.
 */
function castValue(raw: string, fieldType: string): unknown {
  if (raw === '') return undefined
  switch (fieldType) {
    case 'integer': return parseInt(raw, 10)
    case 'float':   return parseFloat(raw)
    case 'boolean': return raw === 'true'
    default:        return raw
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Collapsible metadata form shown above the upload drop-zone.
 *
 * One input field per non-system metadata field defined in the collection
 * schema.  Required fields are visually marked.  On every change the parent
 * receives the full values map so it can pass it directly to ingestDocument.
 *
 * Args:
 *   fields:   Non-system MetaField[] from the collection's config schema.
 *   onChange: Callback receiving the current values map.
 *   isOpen:   Whether the form is visible.
 *   onToggle: Toggle the open/closed state.
 */
export function MetadataInputForm({ fields, onChange, isOpen, onToggle }: MetadataInputFormProps) {
  const [values, setValues] = useState<Record<string, string>>({})

  // Reset values when the field list changes (e.g. collection switch).
  useEffect(() => {
    setValues({})
    onChange({})
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields])

  if (fields.length === 0) return null

  const requiredCount = fields.filter(f => f.required).length
  const filledRequired = fields.filter(f => f.required && values[f.field_name] !== undefined && values[f.field_name] !== '').length

  /**
   * Handles input changes for any field type.
   *
   * Args:
   *   fieldName: The metadata field key being updated.
   *   raw:       The raw string value from the input.
   *   type:      The field_type from the schema (for casting).
   *   checked:   The checked state for boolean checkbox fields.
   */
  function handleChange(fieldName: string, raw: string, type: string, checked?: boolean) {
    // 1. Determine the final raw value.
    const finalRaw = type === 'boolean' ? String(checked ?? false) : raw

    // 2. Update local raw-string state.
    const nextRaw = { ...values, [fieldName]: finalRaw }
    setValues(nextRaw)

    // 3. Build typed output map and emit to parent.
    const typed: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(nextRaw)) {
      const field = fields.find(f => f.field_name === k)
      if (!field || v === '' || v === undefined) continue
      const cast = castValue(v, field.field_type)
      if (cast !== undefined) typed[k] = cast
    }
    onChange(typed)
  }

  return (
    <div className="metadata-form">
      {/* ── Header: toggle + summary ── */}
      <button
        type="button"
        className="metadata-form-toggle"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <span className="metadata-form-chevron">{isOpen ? '▾' : '▸'}</span>
        <span className="metadata-form-label">Metadata</span>
        {requiredCount > 0 && (
          <span className={`metadata-form-status ${filledRequired < requiredCount ? 'metadata-form-status-warn' : 'metadata-form-status-ok'}`}>
            {filledRequired}/{requiredCount} required
          </span>
        )}
      </button>

      {/* ── Fields ── */}
      {isOpen && (
        <div className="metadata-form-body">
          {fields.map(field => {
            const inputType = inputTypeFor(field.field_type)
            const isCheckbox = inputType === 'checkbox'
            const rawVal = values[field.field_name] ?? ''

            return (
              <div key={field.field_name} className="metadata-form-row">
                <label className="metadata-form-field-label" htmlFor={`meta-${field.field_name}`}>
                  {field.field_name}
                  {field.required && <span className="metadata-form-required">*</span>}
                  <span className="metadata-form-type">{field.field_type}</span>
                </label>

                {/* Enum field → select */}
                {field.enum_values && field.enum_values.length > 0 ? (
                  <select
                    id={`meta-${field.field_name}`}
                    className="input input-sm"
                    value={rawVal}
                    onChange={e => handleChange(field.field_name, e.target.value, field.field_type)}
                  >
                    <option value="">— select —</option>
                    {field.enum_values.map(v => (
                      <option key={v} value={v}>{v}</option>
                    ))}
                  </select>
                ) : isCheckbox ? (
                  /* Boolean field → checkbox */
                  <input
                    id={`meta-${field.field_name}`}
                    type="checkbox"
                    checked={rawVal === 'true'}
                    onChange={e => handleChange(field.field_name, '', 'boolean', e.target.checked)}
                  />
                ) : (
                  /* All other types → text / number / date input */
                  <input
                    id={`meta-${field.field_name}`}
                    type={inputType}
                    className="input input-sm"
                    placeholder={field.required ? 'Required' : 'Optional'}
                    value={rawVal}
                    step={field.field_type === 'float' ? 'any' : undefined}
                    onChange={e => handleChange(field.field_name, e.target.value, field.field_type)}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
