// ====== Code Summary ======
// SinglePicker — radio chip group for kind="single"/"optional" dynamic fields.
// The selected choice exposes its conditional param inputs inline; nested
// provider sub-fields (e.g. semantic.embed) reuse a sibling discovery overlay
// via the locally-scoped NestedProviderPicker.

// ====== Internal Project Imports ======
import type { Choice, DiscoveryResponse, DynamicField } from '../../../api/types'
import { FieldInput } from '../FieldInput'

// ====== Local Project Imports ======
import {
  labelFromPath,
  nestedCapabilityFor,
  paramsDefaults,
  type PickerValue,
} from './pickerHelpers'

/**
 * Reuse a sibling chain overlay to render a typed-provider sub-picker.
 *
 * For each create_collection / update_config overlay whose capability matches the
 * one we want (e.g. "embed"), we extract its choices and render a single-picker
 * inline.  The selected ``{id, ...params}`` is written flat into the parent's
 * params under the child field name.
 */
function NestedProviderPicker({
  label, capability, discovery, value, onChange,
}: {
  label: string
  capability: string
  discovery: DiscoveryResponse
  value: Record<string, unknown> | undefined
  onChange: (v: Record<string, unknown>) => void
}) {
  // Find any overlay describing this capability (root-level multi pickers fit).
  const overlay = discovery.endpoints
    .flatMap(e => e.dynamic_fields ?? [])
    .find(df => df != null && df.capability === capability && (df.choices?.length ?? 0) > 0)

  if (!overlay) {
    // No discovery info → degrade to a read-only hint with the current value.
    return (
      <label className="field-row" title={`No discovery overlay for ${capability}`}>
        <span className="field-label">{label}</span>
        <code className="mono" style={{ fontSize: 10, opacity: 0.7 }}>
          {value ? JSON.stringify(value) : '(default)'}
        </code>
      </label>
    )
  }

  const overlayChoices = overlay.choices ?? []
  const selectedId = (value?.id as string | undefined) ?? overlayChoices[0]?.id
  const selected = overlayChoices.find(c => c.id === selectedId) ?? overlayChoices[0]

  function selectChoice(c: Choice) {
    if (!c.selectable) return
    const defaults = paramsDefaults(c.fields ?? [])
    onChange({ id: c.id, ...defaults })
  }

  function updateParam(key: string, v: unknown) {
    onChange({ ...(value ?? { id: selectedId }), [key]: v })
  }

  return (
    <div className="picker" style={{ marginTop: 4 }}>
      <div className="picker-label">{label}</div>
      <div className="picker-chips">
        {overlayChoices.map(c => (
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
      {selected && (selected.fields?.length ?? 0) > 0 && (
        <div className="picker-params fadein">
          {(selected.fields ?? []).map(p => (
            <FieldInput
              key={p.name}
              schema={p}
              value={(value as Record<string, unknown> | undefined)?.[p.name]}
              onChange={v => updateParam(p.name, v)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Radio chip group for a single (or optional) provider/method choice.
 *
 * Args:
 *   field:     Dynamic field descriptor with kind="single" or "optional".
 *   value:     Currently selected value, or null when disabled.
 *   onChange:  Callback to publish the new selection.
 *   label:     Optional override label.
 *   discovery: Optional discovery payload used to resolve nested provider sub-fields.
 */
export function SinglePicker({
  field, value, onChange, label, discovery,
}: {
  field: DynamicField
  value: PickerValue | null | undefined
  onChange: (v: PickerValue | null) => void
  label?: string
  discovery?: DiscoveryResponse
}) {
  const choices = field.choices ?? []
  const defaultChoice = choices.find(c => c.default) ?? choices[0]
  const selectedId = value?.id ?? defaultChoice?.id

  function selectChoice(c: Choice) {
    if (!c.selectable) return
    // Emit a flat object: { id, param1, param2, … } — matches the backend wire format.
    const defaults = paramsDefaults(c.fields ?? [])
    onChange({ id: c.id, ...defaults })
  }

  function updateParam(key: string, v: unknown) {
    // Merge the changed param flat alongside `id`, preserving any existing params.
    onChange({ ...value, id: selectedId!, [key]: v })
  }

  const selectedChoice = choices.find(c => c.id === selectedId)

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
        {choices.map(c => (
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

      {selectedChoice && (selectedChoice.fields?.length ?? 0) > 0 && (
        <div className="picker-params fadein">
          {(selectedChoice.fields ?? []).map(p => {
            // Nested provider config (e.g. semantic.embed) → reuse the sibling overlay
            // to render a proper single-picker instead of a JSON-dict text input.
            const nestedCapability = nestedCapabilityFor(field.capability, p.name)
            // Params are flat alongside `id` in the wire format; cast to read any key.
            const flatValue = value as Record<string, unknown> | null | undefined
            if (nestedCapability && discovery) {
              return (
                <NestedProviderPicker
                  key={p.name}
                  label={p.label || p.name}
                  capability={nestedCapability}
                  discovery={discovery}
                  value={flatValue?.[p.name] as Record<string, unknown> | undefined}
                  onChange={v => updateParam(p.name, v)}
                />
              )
            }
            return (
              <FieldInput
                key={p.name}
                schema={p}
                value={flatValue?.[p.name]}
                onChange={v => updateParam(p.name, v)}
              />
            )
          })}
        </div>
      )}

      {selectedChoice?.note && !selectedChoice.available && (
        <div className="picker-note">{selectedChoice.note}</div>
      )}
    </div>
  )
}
