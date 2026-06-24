// ====== Code Summary ======
// ChoicePicker — thin dispatcher that renders a DynamicField according to its
// `kind`, delegating to a dedicated picker per kind (single/optional/multi/
// map/weights/scalar).  Used by DynamicFieldsGroup and RequestForm; its public
// export is the only entry point — the per-kind pickers live in ./pickers/.

// ====== Internal Project Imports ======
import type { DiscoveryResponse, DynamicField } from '../../api/types'

// ====== Local Project Imports ======
import { MapPicker } from './pickers/MapPicker'
import { MetadataFormPicker } from './pickers/MetadataFormPicker'
import { MultiPicker } from './pickers/MultiPicker'
import type { PickerValue } from './pickers/pickerHelpers'
import { ScalarPicker } from './pickers/ScalarPicker'
import { SinglePicker } from './pickers/SinglePicker'
import { WeightsPicker } from './pickers/WeightsPicker'

interface Props {
  field: DynamicField
  value?: unknown
  onChange: (v: unknown) => void
  label?: string
  // Forwarded so SinglePicker can resolve nested-provider choices (e.g. semantic.embed).
  // Optional — when absent, nested provider fields fall back to a JSON-ish FieldInput.
  discovery?: DiscoveryResponse
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
export function ChoicePicker({ field, value, onChange, label, discovery }: Props) {
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
        discovery={discovery}
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

  if (field.kind === 'scalar') {
    return (
      <ScalarPicker
        field={field}
        value={value}
        onChange={onChange}
        label={label}
      />
    )
  }

  return null
}
