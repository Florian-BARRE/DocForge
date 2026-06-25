// ====== Code Summary ======
// ScalarPicker — renders a stage-level pipeline param (chart_to_data, …)
// for kind="scalar" dynamic fields as a single FieldInput.

// ====== Internal Project Imports ======
import type { DynamicField } from '../../../api/types'
import { FieldInput } from '../FieldInput'

/**
 * Render a stage-level pipeline param as a single FieldInput.
 *
 * The transport wraps the scalar in a single Choice with one field so the
 * existing schema infrastructure can carry typed defaults/bounds without a
 * separate shape.
 *
 * Args:
 *   field:    Dynamic field descriptor with kind="scalar".
 *   value:    Current scalar value.
 *   onChange: Callback to publish the new value.
 *   label:    Optional override label.
 */
export function ScalarPicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: unknown
  onChange: (v: unknown) => void
  label?: string
}) {
  const choice = (field.choices ?? [])[0]
  const spec = choice?.fields?.[0]
  if (!spec) return null
  return (
    <FieldInput
      schema={{ ...spec, label: label || choice.label || spec.label || spec.name }}
      value={value}
      onChange={onChange}
    />
  )
}
