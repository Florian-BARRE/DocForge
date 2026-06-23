// ====== Code Summary ======
// SearchFilterBuilder — interactive editor that lets the user assemble a Qdrant
// payload filter from a collection's filterable metadata fields. Each condition
// targets a clause (must / should / must_not), a field, an operator chosen from
// the field type, and a value. The component groups conditions by clause and
// emits a Qdrant-compatible filter object (or null when empty) via onChange.

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { MetaField } from '../../api/types'

// ── Types ─────────────────────────────────────────────────────────────────────

/** Boolean clause a condition belongs to in the Qdrant filter. */
type FilterClause = 'must' | 'should' | 'must_not'

/** Operator applied to a field — drives whether a match or range is emitted. */
type FilterOp = 'match' | 'gte' | 'lte'

/** A single user-defined filter condition. */
interface FilterCondition {
  /** Stable local id used as the React key. */
  id: string
  clause: FilterClause
  field: string
  op: FilterOp
  /** Raw string value from the input; coerced per field type at build time. */
  value: string
}

interface SearchFilterBuilderProps {
  /** Collection metadata fields (configState.metadata_fields). */
  fields: MetaField[]
  /** Emits the Qdrant payload filter, or null when no condition is set. */
  onChange: (filter: Record<string, unknown> | null) => void
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Return the operators available for a given field type.
 *
 * Args:
 *   fieldType: The metadata field's declared type (string/integer/float/boolean/date).
 *
 * Returns:
 *   FilterOp[]: Allowed operators for that type.
 */
function operatorsForType(fieldType: string): FilterOp[] {
  switch (fieldType) {
    case 'integer':
    case 'float':
      return ['match', 'gte', 'lte']
    case 'date':
      return ['gte', 'lte']
    case 'boolean':
    case 'string':
    default:
      return ['match']
  }
}

/**
 * Coerce a raw string value into the type expected by the field.
 *
 * Args:
 *   field: The targeted metadata field (provides field_type).
 *   raw:   Raw string from the value input.
 *
 * Returns:
 *   unknown: The coerced value (number, boolean, or string).
 */
function coerceValue(field: MetaField, raw: string): unknown {
  switch (field.field_type) {
    case 'integer':
      return parseInt(raw, 10)
    case 'float':
      return parseFloat(raw)
    case 'boolean':
      return raw === 'true'
    default:
      return raw
  }
}

/**
 * Build the per-condition Qdrant clause entry (match or range).
 *
 * Args:
 *   field: Targeted metadata field (drives value coercion).
 *   op:    Operator selected for the condition.
 *   value: Coerced condition value.
 *
 * Returns:
 *   Record<string, unknown>: A Qdrant field condition object.
 */
function buildConditionEntry(
  field: MetaField,
  op: FilterOp,
  value: unknown,
): Record<string, unknown> {
  // 1. Equality → match condition.
  if (op === 'match') {
    return { key: field.field_name, match: { value } }
  }
  // 2. Bounded comparison → range condition.
  return { key: field.field_name, range: { [op]: value } }
}

/**
 * Assemble the full Qdrant payload filter from a list of conditions.
 *
 * Conditions are grouped by clause; empty clauses are omitted. When no condition
 * yields a usable value, null is returned so callers can drop the filter entirely.
 *
 * Args:
 *   conditions: Current user-defined conditions.
 *   fieldMap:   Lookup of field_name → MetaField for value coercion.
 *
 * Returns:
 *   Record<string, unknown> | null: Qdrant filter, or null when empty.
 */
function buildFilter(
  conditions: FilterCondition[],
  fieldMap: Map<string, MetaField>,
): Record<string, unknown> | null {
  // 1. Bucket each valid condition under its clause.
  const buckets: Record<FilterClause, Record<string, unknown>[]> = {
    must: [],
    should: [],
    must_not: [],
  }

  for (const cond of conditions) {
    const field = fieldMap.get(cond.field)
    if (!field) continue
    if (cond.value.trim() === '') continue
    const value = coerceValue(field, cond.value)
    buckets[cond.clause].push(buildConditionEntry(field, cond.op, value))
  }

  // 2. Drop empty clauses; bail out entirely when nothing is set.
  const filter: Record<string, unknown> = {}
  for (const clause of ['must', 'should', 'must_not'] as FilterClause[]) {
    if (buckets[clause].length > 0) filter[clause] = buckets[clause]
  }
  return Object.keys(filter).length > 0 ? filter : null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Qdrant payload filter builder for a collection's filterable metadata fields.
 *
 * Only fields flagged `filterable` are offered (they are the only payload-indexed
 * fields). The user adds rows, each picking a clause / field / operator / value;
 * the assembled filter is emitted via onChange on every change.
 *
 * Args:
 *   fields:   All collection metadata fields (filtered to filterable here).
 *   onChange: Callback receiving the Qdrant filter object or null.
 */
export function SearchFilterBuilder({ fields, onChange }: SearchFilterBuilderProps) {
  const filterableFields = fields.filter(f => f.filterable)
  const fieldMap = new Map(filterableFields.map(f => [f.field_name, f]))

  const [conditions, setConditions] = useState<FilterCondition[]>([])

  // Re-emit the assembled filter whenever conditions change.
  useEffect(() => {
    onChange(buildFilter(conditions, fieldMap))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conditions])

  // ── Mutators ────────────────────────────────────────────────────────────────

  /**
   * Append a new condition seeded with the first available field.
   */
  function addCondition() {
    const first = filterableFields[0]
    if (!first) return
    setConditions(prev => [
      ...prev,
      {
        id: `${Date.now()}-${prev.length}`,
        clause: 'must',
        field: first.field_name,
        op: operatorsForType(first.field_type)[0],
        value: '',
      },
    ])
  }

  /**
   * Patch a single condition by id, resetting the operator when the field
   * changes so the operator stays valid for the new field type.
   *
   * Args:
   *   id:    Target condition id.
   *   patch: Partial condition fields to merge.
   */
  function updateCondition(id: string, patch: Partial<FilterCondition>) {
    setConditions(prev =>
      prev.map(cond => {
        if (cond.id !== id) return cond
        const merged = { ...cond, ...patch }
        // When the field changed, snap the operator to a valid one.
        if (patch.field) {
          const field = fieldMap.get(patch.field)
          if (field) merged.op = operatorsForType(field.field_type)[0]
        }
        return merged
      }),
    )
  }

  /**
   * Remove a condition by id.
   *
   * Args:
   *   id: Target condition id.
   */
  function removeCondition(id: string) {
    setConditions(prev => prev.filter(cond => cond.id !== id))
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (filterableFields.length === 0) {
    return (
      <div className="stage-config-empty" style={{ fontSize: 11 }}>
        No filterable fields in this collection.
      </div>
    )
  }

  return (
    <div className="filter-builder">
      {conditions.map(cond => {
        const field = fieldMap.get(cond.field)
        return (
          <div className="filter-row" key={cond.id}>
            {/* Clause */}
            <select
              value={cond.clause}
              onChange={e => updateCondition(cond.id, { clause: e.target.value as FilterClause })}
            >
              <option value="must">must</option>
              <option value="should">should</option>
              <option value="must_not">must not</option>
            </select>

            {/* Field */}
            <select
              value={cond.field}
              onChange={e => updateCondition(cond.id, { field: e.target.value })}
            >
              {filterableFields.map(f => (
                <option key={f.field_name} value={f.field_name}>{f.field_name}</option>
              ))}
            </select>

            {/* Operator */}
            <select
              value={cond.op}
              onChange={e => updateCondition(cond.id, { op: e.target.value as FilterOp })}
            >
              {operatorsForType(field?.field_type ?? 'string').map(op => (
                <option key={op} value={op}>{op}</option>
              ))}
            </select>

            {/* Value — input shape depends on field type */}
            <FilterValueInput
              field={field}
              value={cond.value}
              onChange={v => updateCondition(cond.id, { value: v })}
            />

            {/* Remove */}
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => removeCondition(cond.id)}
              aria-label="Remove condition"
            >
              ×
            </button>
          </div>
        )
      })}

      <div>
        <button type="button" className="btn btn-ghost" onClick={addCondition}>
          + Add filter
        </button>
      </div>
    </div>
  )
}

// ── FilterValueInput ───────────────────────────────────────────────────────────

interface FilterValueInputProps {
  /** Field being filtered, or undefined while resolving. */
  field: MetaField | undefined
  value: string
  onChange: (value: string) => void
}

/**
 * Render the appropriate value control for a field type.
 *
 * Enum strings render a value picker; booleans render a true/false select;
 * numbers render a number input; dates render a date input; everything else
 * falls back to a free text input.
 *
 * Args:
 *   field:    The targeted metadata field (drives the input variant).
 *   value:    Current raw value.
 *   onChange: Callback receiving the new raw value.
 */
function FilterValueInput({ field, value, onChange }: FilterValueInputProps) {
  if (!field) {
    return <input className="input" value={value} onChange={e => onChange(e.target.value)} />
  }

  // 1. Enum string → value picker.
  if (field.field_type === 'string' && field.enum_values && field.enum_values.length > 0) {
    return (
      <select value={value} onChange={e => onChange(e.target.value)}>
        <option value="">—</option>
        {field.enum_values.map(v => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
    )
  }

  // 2. Boolean → true/false select.
  if (field.field_type === 'boolean') {
    return (
      <select value={value} onChange={e => onChange(e.target.value)}>
        <option value="">—</option>
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    )
  }

  // 3. Numeric → number input.
  if (field.field_type === 'integer' || field.field_type === 'float') {
    return (
      <input
        className="input"
        type="number"
        value={value}
        onChange={e => onChange(e.target.value)}
      />
    )
  }

  // 4. Date → date input.
  if (field.field_type === 'date') {
    return (
      <input
        className="input"
        type="date"
        value={value}
        onChange={e => onChange(e.target.value)}
      />
    )
  }

  // 5. Fallback → free text.
  return (
    <input
      className="input"
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
    />
  )
}
