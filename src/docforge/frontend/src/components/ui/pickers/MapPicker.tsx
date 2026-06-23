// ====== Code Summary ======
// MapPicker — key→value editor for kind="map" dynamic fields (search filters).
// Each row encodes a "{fieldId}::{op}" key with a JSON-parsed value, producing a
// flat Record<string, unknown> object on change.

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import type { DynamicField } from '../../../api/types'

// ====== Local Project Imports ======
import { labelFromPath } from './pickerHelpers'

interface FilterEntry { fieldId: string; op: string; val: string }

/**
 * Key→value filter builder for a map dynamic field.
 *
 * Args:
 *   field:    Dynamic field descriptor with kind="map".
 *   value:    Current filter object keyed by "{fieldId}::{op}".
 *   onChange: Callback to publish the rebuilt filter object.
 *   label:    Optional override label.
 */
export function MapPicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: Record<string, unknown> | undefined
  onChange: (v: Record<string, unknown>) => void
  label?: string
}) {
  const [entries, setEntries] = useState<FilterEntry[]>(() => {
    if (!value) return []
    return Object.entries(value).map(([k, v]) => {
      const parts = k.split('::')
      return { fieldId: parts[0], op: parts[1] ?? 'eq', val: JSON.stringify(v) }
    })
  })

  function sync(next: FilterEntry[]) {
    setEntries(next)
    const built: Record<string, unknown> = {}
    next.forEach(e => {
      if (e.fieldId && e.val) {
        const key = `${e.fieldId}::${e.op}`
        try { built[key] = JSON.parse(e.val) } catch { built[key] = e.val }
      }
    })
    onChange(built)
  }

  function addEntry() {
    sync([...entries, { fieldId: '', op: 'eq', val: '' }])
  }

  function updateEntry(idx: number, patch: Partial<FilterEntry>) {
    sync(entries.map((e, i) => i === idx ? { ...e, ...patch } : e))
  }

  function removeEntry(idx: number) {
    sync(entries.filter((_, i) => i !== idx))
  }

  const fieldIds = field.choices.map(c => c.id)

  return (
    <div className="picker">
      <div className="picker-label">{label || labelFromPath(field.field_path)}</div>
      {entries.map((entry, idx) => {
        const choice = field.choices.find(c => c.id === entry.fieldId)
        const opField = choice?.fields.find(f => f.name === 'op')
        const ops = opField?.enum ?? ['eq']
        return (
          <div key={idx} className="filter-row">
            <select
              className="input select"
              value={entry.fieldId}
              onChange={e => updateEntry(idx, { fieldId: e.target.value, op: 'eq' })}
              style={{ width: 140 }}
            >
              <option value="">— field —</option>
              {fieldIds.map(id => <option key={id} value={id}>{id}</option>)}
            </select>
            <select
              className="input select"
              value={entry.op}
              onChange={e => updateEntry(idx, { op: e.target.value })}
              style={{ width: 80 }}
            >
              {ops.map(op => <option key={op} value={op}>{op}</option>)}
            </select>
            <input
              className="input"
              value={entry.val}
              onChange={e => updateEntry(idx, { val: e.target.value })}
              placeholder='value or ["a","b"]'
              style={{ flex: 1 }}
            />
            <button className="btn btn-ghost btn-danger" onClick={() => removeEntry(idx)} type="button">✕</button>
          </div>
        )
      })}
      <button className="btn" style={{ marginTop: 6, fontSize: 12 }} onClick={addEntry} type="button">
        + add filter
      </button>
    </div>
  )
}
