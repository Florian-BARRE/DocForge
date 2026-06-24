// ====== Code Summary ======
// MultiPicker — ordered list builder for kind="multi" dynamic fields
// (e.g. the OCR escalation chain).  Each appended choice can expand to edit its
// own params; entries can be removed.

// ====== Standard Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import type { Choice, DynamicField } from '../../../api/types'
import { FieldInput } from '../FieldInput'

// ====== Local Project Imports ======
import { labelFromPath, paramsDefaults, type PickerValue } from './pickerHelpers'

/**
 * Ordered chain builder for a multi-choice dynamic field.
 *
 * Args:
 *   field:    Dynamic field descriptor with kind="multi".
 *   value:    Current ordered list of selected values.
 *   onChange: Callback to publish the new chain.
 *   label:    Optional override label.
 */
export function MultiPicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: PickerValue[] | undefined
  onChange: (v: PickerValue[]) => void
  label?: string
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const chain = value ?? []

  function add(c: Choice) {
    const defaults = paramsDefaults(c.fields)
    onChange([...chain, { id: c.id, params: Object.keys(defaults).length ? defaults : undefined }])
  }

  function remove(idx: number) {
    onChange(chain.filter((_, i) => i !== idx))
  }

  function updateParam(idx: number, key: string, v: unknown) {
    const next = chain.map((item, i) =>
      i === idx ? { ...item, params: { ...item.params, [key]: v } } : item
    )
    onChange(next)
  }

  const available = field.choices.filter(c => c.available && c.selectable)

  return (
    <div className="picker">
      <div className="picker-label">{label || labelFromPath(field.field_path)}</div>

      {chain.length > 0 && (
        <div className="chain-list">
          {chain.map((item, idx) => {
            const choice = field.choices.find(c => c.id === item.id)
            const isOpen = expanded === `${idx}`
            return (
              <div key={idx} className="chain-item">
                <div className="chain-item-row">
                  <span className="chain-rank mono">{idx + 1}</span>
                  <span className="chain-id">{choice?.label || item.id}</span>
                  {choice && choice.fields.length > 0 && (
                    <button
                      className="btn btn-ghost"
                      style={{ fontSize: 11, padding: '2px 6px' }}
                      onClick={() => setExpanded(isOpen ? null : `${idx}`)}
                      type="button"
                    >
                      {isOpen ? '▲' : '▼'} params
                    </button>
                  )}
                  <button className="btn btn-ghost btn-danger" onClick={() => remove(idx)} type="button">✕</button>
                </div>
                {isOpen && choice && choice.fields.length > 0 && (
                  <div className="picker-params fadein" style={{ marginLeft: 28 }}>
                    {choice.fields.map(p => (
                      <FieldInput
                        key={p.name}
                        schema={p}
                        value={(item.params ?? {})[p.name]}
                        onChange={v => updateParam(idx, p.name, v)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {available.length > 0 && (
        <div className="picker-chips" style={{ marginTop: 8 }}>
          <span className="text-muted" style={{ fontSize: 11 }}>+ add</span>
          {available.map(c => (
            <button
              key={c.id}
              className="chip"
              onClick={() => add(c)}
              type="button"
            >
              {c.label || c.id}
            </button>
          ))}
        </div>
      )}

      {chain.length === 0 && available.length === 0 && (
        <div className="picker-note">No providers available in this deployment.</div>
      )}
    </div>
  )
}
