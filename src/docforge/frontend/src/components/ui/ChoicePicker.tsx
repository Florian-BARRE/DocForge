import { useState } from 'react'
import type { Choice, DynamicField, ParamSchema } from '../../api/types'
import { FieldInput } from './FieldInput'

interface PickerValue {
  id: string
  params?: Record<string, unknown>
}

interface Props {
  field: DynamicField
  value?: unknown
  onChange: (v: unknown) => void
  label?: string
}

/**
 * Renders a dynamic field: provider/method picker with conditional param inputs.
 *
 * kind="single"   → radio button group, selected option shows its params inline
 * kind="optional" → same as single but can be null (disabled)
 * kind="multi"    → ordered list builder (OCR chain etc.)
 * kind="map"      → key→value filter builder (search filters)
 * kind="weights"  → float slider per named vector
 */
export function ChoicePicker({ field, value, onChange, label }: Props) {
  if (!field.resolved) {
    return (
      <div className="picker-unresolved">
        <span className="text-muted">{label || field.field_path}</span>
        <span className="tag" style={{ marginLeft: 8 }}>collection required</span>
      </div>
    )
  }

  if (field.kind === 'single' || field.kind === 'optional') {
    return (
      <SinglePicker
        field={field}
        value={value as PickerValue | null | undefined}
        onChange={onChange as unknown as (v: PickerValue | null) => void}
        label={label}
      />
    )
  }

  if (field.kind === 'multi') {
    return (
      <MultiPicker
        field={field}
        value={value as PickerValue[] | undefined}
        onChange={onChange as unknown as (v: PickerValue[]) => void}
        label={label}
      />
    )
  }

  if (field.kind === 'map') {
    if (field.capability === 'metadata_write') {
      return (
        <MetadataFormPicker
          field={field}
          value={value as Record<string, unknown> | undefined}
          onChange={onChange as unknown as (v: Record<string, unknown>) => void}
          label={label}
        />
      )
    }
    return (
      <MapPicker
        field={field}
        value={value as Record<string, unknown> | undefined}
        onChange={onChange as unknown as (v: Record<string, unknown>) => void}
        label={label}
      />
    )
  }

  if (field.kind === 'weights') {
    return (
      <WeightsPicker
        field={field}
        value={value as Record<string, number> | undefined}
        onChange={onChange as unknown as (v: Record<string, number>) => void}
        label={label}
      />
    )
  }

  return null
}

// ── Single / optional picker ─────────────────────────────────────────────────

function SinglePicker({
  field, value, onChange, label,
}: {
  field: DynamicField
  value: PickerValue | null | undefined
  onChange: (v: PickerValue | null) => void
  label?: string
}) {
  const defaultChoice = field.choices.find(c => c.default) ?? field.choices[0]
  const selectedId = value?.id ?? defaultChoice?.id

  function selectChoice(c: Choice) {
    if (!c.selectable) return
    const defaults = paramsDefaults(c.fields)
    onChange({ id: c.id, params: Object.keys(defaults).length ? defaults : undefined })
  }

  function updateParam(key: string, v: unknown) {
    const params = { ...(value?.params ?? {}), [key]: v }
    onChange({ id: selectedId!, params })
  }

  const selectedChoice = field.choices.find(c => c.id === selectedId)

  return (
    <div className="picker">
      <div className="picker-label">{label || labelFromPath(field.field_path)}</div>
      <div className="picker-chips">
        {field.kind === 'optional' && (
          <button
            className={`chip ${!selectedId ? 'chip-active' : ''}`}
            onClick={() => onChange(null)}
            type="button"
          >
            disabled
          </button>
        )}
        {field.choices.map(c => (
          <button
            key={c.id}
            className={`chip ${c.id === selectedId ? 'chip-active' : ''} ${!c.available ? 'chip-unavailable' : ''}`}
            onClick={() => selectChoice(c)}
            title={c.note || (!c.available ? 'Not available in this deployment' : undefined)}
            type="button"
            disabled={!c.selectable}
          >
            {c.label || c.id}
            {!c.available && <span className="chip-dot chip-dot-off" />}
          </button>
        ))}
      </div>

      {selectedChoice && selectedChoice.fields.length > 0 && (
        <div className="picker-params fadein">
          {selectedChoice.fields.map(p => (
            <FieldInput
              key={p.name}
              schema={p}
              value={(value?.params ?? {})[p.name]}
              onChange={v => updateParam(p.name, v)}
            />
          ))}
        </div>
      )}

      {selectedChoice?.note && !selectedChoice.available && (
        <div className="picker-note">{selectedChoice.note}</div>
      )}
    </div>
  )
}

// ── Multi / chain picker ─────────────────────────────────────────────────────

function MultiPicker({
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

// ── Map picker (search filters) ───────────────────────────────────────────────

interface FilterEntry { fieldId: string; op: string; val: string }

function MapPicker({
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

// ── Weights picker ────────────────────────────────────────────────────────────

function WeightsPicker({
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

// ── Metadata form picker (kind=map + capability=metadata_write) ───────────────
// One typed input per custom field, with type badge and required/optional indicator.
// Produces { field_name: value } (no operator — raw metadata object for ingest).

function MetadataFormPicker({
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

// ── Utilities ─────────────────────────────────────────────────────────────────

function paramsDefaults(fields: ParamSchema[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  fields.forEach(f => { if (f.default !== undefined && f.default !== null) out[f.name] = f.default })
  return out
}

function labelFromPath(path: string): string {
  const last = path.split('.').pop() ?? path
  return last.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
