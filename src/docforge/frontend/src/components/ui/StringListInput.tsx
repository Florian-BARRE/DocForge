// ====== Code Summary ======
// Chip-style editor for `array<string>` JSON-Schema fields.  Lifted out of CollectionStep
// so every form that needs a string list (supported_formats, enum_values, allowed_providers,
// …) shares the same control without re-implementing tokenisation/backspace handling.

import { useState } from 'react'

interface Props {
  name: string
  label: string
  description: string
  value: string[]
  onChange: (v: string[]) => void
}

export function StringListInput({ name, label, description, value, onChange }: Props) {
  const [draft, setDraft] = useState('')

  function commit(text: string) {
    const parts = text.split(/[\s,]+/).map(s => s.trim()).filter(Boolean)
    if (parts.length === 0) return
    onChange(Array.from(new Set([...value, ...parts])))
    setDraft('')
  }

  function remove(idx: number) {
    onChange(value.filter((_, i) => i !== idx))
  }

  return (
    <label className="field-row" title={description}>
      <span className="field-label">{label}</span>
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 4, flex: 1,
        minHeight: 28, alignItems: 'center',
      }}>
        {value.map((v, i) => (
          <span
            key={`${v}-${i}`}
            className="tag"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
          >
            <span>{v}</span>
            <button
              type="button"
              className="btn-icon"
              onClick={() => remove(i)}
              style={{ fontSize: 10, padding: 0, lineHeight: 1 }}
              aria-label={`Remove ${v}`}
            >✕</button>
          </span>
        ))}
        <input
          className="input"
          type="text"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault()
              commit(draft)
            } else if (e.key === 'Backspace' && !draft && value.length > 0) {
              remove(value.length - 1)
            }
          }}
          onBlur={() => draft && commit(draft)}
          placeholder={value.length === 0 ? `${name} (comma-separated)` : '+ add'}
          style={{ flex: 1, minWidth: 100 }}
        />
      </div>
    </label>
  )
}
