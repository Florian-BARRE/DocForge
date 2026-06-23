// ====== Code Summary ======
// WeightsPicker — float slider per named vector for kind="weights" dynamic fields.
// Produces a Record<string, number> keyed by choice id.

// ====== Internal Project Imports ======
import type { DynamicField } from '../../../api/types'

// ====== Local Project Imports ======
import { labelFromPath } from './pickerHelpers'

/**
 * Slider grid assigning a float weight to each named choice.
 *
 * Args:
 *   field:    Dynamic field descriptor with kind="weights".
 *   value:    Current weights keyed by choice id.
 *   onChange: Callback to publish the updated weights.
 *   label:    Optional override label.
 */
export function WeightsPicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: Record<string, number> | undefined
  onChange: (v: Record<string, number>) => void
  label?: string
}) {
  const current = value ?? {}

  function update(id: string, v: number) {
    onChange({ ...current, [id]: v })
  }

  return (
    <div className="picker">
      <div className="picker-label">{label || labelFromPath(field.field_path)}</div>
      {field.choices.map(c => {
        const w = current[c.id] ?? (c.fields[0]?.default as number ?? 1.0)
        return (
          <div key={c.id} className="weight-row">
            <span className="weight-id mono">{c.id}</span>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={w}
              onChange={e => update(c.id, parseFloat(e.target.value))}
              className="weight-slider"
            />
            <span className="weight-val mono">{w.toFixed(2)}</span>
          </div>
        )
      })}
    </div>
  )
}
