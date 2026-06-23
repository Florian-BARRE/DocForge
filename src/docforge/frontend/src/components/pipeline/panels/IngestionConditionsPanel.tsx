// ====== Code Summary ======
// Editable ingestion conditions panel for the S0 stage.
// Displays and allows editing of top-level collection config fields:
// supported_formats, max_file_size_bytes, unknown_field_policy, and
// metadata_fields (user-defined only; system fields are read-only).
// Edits accumulate in a local draft buffer (useConfigDraft) and are persisted
// only when the user clicks Save in the ConfigSaveBar at the bottom.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'
import type { KeyboardEvent } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState, MetaField } from '../../../api/types'
import { useConfigDraft } from '../../../hooks/useConfigDraft'
import { ConfigSaveBar } from '../../ui/ConfigSaveBar'

// ── Types ─────────────────────────────────────────────────────────────────────

interface IngestionConditionsPanelProps {
  /** Current collection config containing the ingestion conditions. */
  configState: ConfigState
  /** Collection ID used when persisting changes. */
  collectionId: string
  /** Called after a successful save so the parent can refresh its copy. */
  onSaved?: () => void
}

/** Field types available when adding a new metadata field. */
const FIELD_TYPES = ['string', 'integer', 'float', 'boolean', 'date', 'list'] as const

/** Common unknown-field policy values surfaced as a select. */
const UNKNOWN_FIELD_POLICIES = ['reject', 'ignore', 'allow'] as const

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Editable ingestion conditions panel.
 *
 * Covers four top-level ConfigState fields:
 *   - supported_formats   → tag-chip input (add / remove)
 *   - max_file_size_bytes → number input in MB
 *   - unknown_field_policy → select
 *   - metadata_fields      → editable table (user fields) + read-only system rows
 *
 * Edits stage a top-level patch into the shared draft buffer; nothing is sent to
 * the server until the user clicks Save in the bottom ConfigSaveBar. Discard (or
 * a successful save) re-seeds the local form state from configState.
 *
 * Args:
 *   configState:  Current collection config.
 *   collectionId: Target collection.
 *   onSaved:      Callback fired after a successful save.
 */
export function IngestionConditionsPanel({
  configState,
  collectionId,
  onSaved,
}: IngestionConditionsPanelProps) {
  // ── Draft buffer (shared explicit save/discard workflow) ──────────────────
  const draft = useConfigDraft(collectionId, onSaved)

  // ── Local state seeded from configState ───────────────────────────────────

  const [formats, setFormats] = useState<string[]>(() => configState.supported_formats)
  const [maxSizeMb, setMaxSizeMb] = useState<number>(
    () => Math.round(configState.max_file_size_bytes / (1024 * 1024))
  )
  const [unknownPolicy, setUnknownPolicy] = useState(configState.unknown_field_policy)
  const [metaFields, setMetaFields] = useState<MetaField[]>(() => configState.metadata_fields)

  // Reset nonce: bumped when configState changes OR on local discard, so the
  // seed effect below can restore local form state from the persisted config.
  const [resetNonce, setResetNonce] = useState(0)

  // Bump the nonce whenever the parent provides a fresh configState.
  useEffect(() => {
    setResetNonce(n => n + 1)
  }, [configState])

  // Re-seed local form state from configState on mount, parent refresh, or discard.
  useEffect(() => {
    setFormats(configState.supported_formats)
    setMaxSizeMb(Math.round(configState.max_file_size_bytes / (1024 * 1024)))
    setUnknownPolicy(configState.unknown_field_policy)
    setMetaFields(configState.metadata_fields)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetNonce])

  /** Discard the draft buffer and re-seed local form state from configState. */
  function handleDiscard() {
    draft.discard()
    setResetNonce(n => n + 1)
  }

  // ── Format chip input ─────────────────────────────────────────────────────

  const [formatInput, setFormatInput] = useState('')

  /**
   * Adds a new format from the input field on Enter or comma.
   *
   * Args:
   *   e: Keyboard event on the format text input.
   */
  function handleFormatKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key !== 'Enter' && e.key !== ',') return
    e.preventDefault()
    const val = formatInput.trim().toLowerCase()
    if (!val || formats.includes(val)) {
      setFormatInput('')
      return
    }
    const next = [...formats, val]
    setFormats(next)
    setFormatInput('')
    draft.stage({ supported_formats: next })
  }

  /**
   * Removes a format chip by value.
   *
   * Args:
   *   fmt: The format string to remove.
   */
  function removeFormat(fmt: string) {
    const next = formats.filter(f => f !== fmt)
    setFormats(next)
    draft.stage({ supported_formats: next })
  }

  // ── Max file size ─────────────────────────────────────────────────────────

  /**
   * Handles MB input change, converts to bytes for the patch.
   *
   * Args:
   *   val: New MB value from the number input.
   */
  function handleMaxSizeChange(val: number) {
    setMaxSizeMb(val)
    draft.stage({ max_file_size_bytes: val * 1024 * 1024 })
  }

  // ── Unknown field policy ──────────────────────────────────────────────────

  /**
   * Handles unknown-field policy select change.
   *
   * Args:
   *   val: Selected policy string.
   */
  function handlePolicyChange(val: string) {
    setUnknownPolicy(val)
    draft.stage({ unknown_field_policy: val })
  }

  // ── Metadata fields table ─────────────────────────────────────────────────

  const userFields  = metaFields.filter(f => !f.is_system)
  const systemFields = metaFields.filter(f =>  f.is_system)

  /**
   * Updates a single property of a user-defined metadata field by index.
   *
   * Args:
   *   idx:  Index within the userFields array (not the full metaFields array).
   *   key:  Property name to update.
   *   val:  New value.
   */
  function updateUserField(idx: number, key: keyof MetaField, val: unknown) {
    const next = userFields.map((f, i) => i === idx ? { ...f, [key]: val } : f)
    const merged = [...next, ...systemFields]
    setMetaFields(merged)
    draft.stage({ metadata_fields: merged })
  }

  /**
   * Removes a user-defined metadata field by index.
   *
   * Args:
   *   idx: Index within the userFields array.
   */
  function removeUserField(idx: number) {
    const next = userFields.filter((_, i) => i !== idx)
    const merged = [...next, ...systemFields]
    setMetaFields(merged)
    draft.stage({ metadata_fields: merged })
  }

  /** Appends a blank user-defined metadata field row. */
  function addField() {
    const blank: MetaField = {
      field_name: '',
      field_type: 'string',
      required: false,
      filterable: false,
      lexical: false,
      semantic: false,
      is_system: false,
    }
    const next = [...userFields, blank]
    const merged = [...next, ...systemFields]
    setMetaFields(merged)
    // Don't stage yet — user must fill in field_name first.
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="stage-conditions">
      {/* ── Supported formats ── */}
      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Accepted formats</div>
        <div className="stage-conditions-chips" style={{ marginBottom: 6 }}>
          {formats.map(f => (
            <span key={f} className="tag tag-removable">
              {f}
              <button
                type="button"
                className="tag-remove"
                aria-label={`Remove ${f}`}
                onClick={() => removeFormat(f)}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        <input
          type="text"
          className="input input-sm"
          placeholder="Add format (e.g. application/pdf) — Enter to add"
          value={formatInput}
          onChange={e => setFormatInput(e.target.value)}
          onKeyDown={handleFormatKeyDown}
        />
      </div>

      {/* ── Limits ── */}
      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Limits</div>

        <div className="stage-panel-row">
          <label className="stage-panel-label" htmlFor="max-size-mb">Max file size (MB)</label>
          <input
            id="max-size-mb"
            type="number"
            className="input input-sm input-inline"
            min={1}
            step={1}
            value={maxSizeMb}
            onChange={e => handleMaxSizeChange(Number(e.target.value))}
          />
        </div>

        <div className="stage-panel-row">
          <label className="stage-panel-label" htmlFor="unknown-policy">Unknown fields</label>
          <select
            id="unknown-policy"
            className="input input-sm input-inline"
            value={unknownPolicy}
            onChange={e => handlePolicyChange(e.target.value)}
          >
            {UNKNOWN_FIELD_POLICIES.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
            {/* Show custom value if it doesn't match the presets */}
            {!UNKNOWN_FIELD_POLICIES.includes(unknownPolicy as typeof UNKNOWN_FIELD_POLICIES[number]) && (
              <option value={unknownPolicy}>{unknownPolicy}</option>
            )}
          </select>
        </div>
      </div>

      {/* ── Metadata schema ── */}
      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Metadata schema</div>

        <table className="stage-conditions-table meta-schema-table">
          <thead>
            <tr>
              <th>Field</th>
              <th>Type</th>
              <th title="Required — must be provided at ingestion">Req.</th>
              <th title="Filterable — available as a search filter">Flt.</th>
              <th title="Lexical — included in full-text BM25 search">Lex.</th>
              <th title="Semantic — embedded for vector search">Sem.</th>
              <th title="Origin of the field">Origin</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {/* User-defined editable rows — shown first */}
            {userFields.map((f, idx) => (
              <tr key={idx} className="meta-schema-row-user">
                <td>
                  <input
                    type="text"
                    className="input input-sm input-table"
                    placeholder="field_name"
                    value={f.field_name}
                    onChange={e => updateUserField(idx, 'field_name', e.target.value)}
                    onBlur={e => {
                      // Only stage when field_name is non-empty to avoid orphan rows.
                      if (e.target.value.trim()) {
                        draft.stage({ metadata_fields: [...userFields, ...systemFields] })
                      }
                    }}
                  />
                </td>
                <td>
                  <select
                    className="input input-sm input-table"
                    value={f.field_type}
                    onChange={e => updateUserField(idx, 'field_type', e.target.value)}
                  >
                    {FIELD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td className="meta-schema-check">
                  <input type="checkbox" checked={f.required}    onChange={e => updateUserField(idx, 'required',    e.target.checked)} />
                </td>
                <td className="meta-schema-check">
                  <input type="checkbox" checked={f.filterable}  onChange={e => updateUserField(idx, 'filterable',  e.target.checked)} />
                </td>
                <td className="meta-schema-check">
                  <input type="checkbox" checked={f.lexical}     onChange={e => updateUserField(idx, 'lexical',     e.target.checked)} />
                </td>
                <td className="meta-schema-check">
                  <input type="checkbox" checked={f.semantic}    onChange={e => updateUserField(idx, 'semantic',    e.target.checked)} />
                </td>
                <td>
                  <span className="tag meta-tag-user">user</span>
                </td>
                <td>
                  <button type="button" className="btn-icon" aria-label="Remove field" onClick={() => removeUserField(idx)}>×</button>
                </td>
              </tr>
            ))}

            {/* System fields — read-only, clearly labeled */}
            {systemFields.map(f => (
              <tr key={f.field_name} className="stage-conditions-row-system meta-schema-row-system">
                <td className="mono">{f.field_name}</td>
                <td>{f.field_type}{f.enum_values && f.enum_values.length > 0 && (
                  <span className="meta-enum-hint" title={f.enum_values.join(', ')}> [{f.enum_values.join('|')}]</span>
                )}</td>
                <td className="meta-schema-check">{f.required   ? <span className="meta-flag meta-flag-on">✓</span> : <span className="meta-flag">—</span>}</td>
                <td className="meta-schema-check">{f.filterable ? <span className="meta-flag meta-flag-on">✓</span> : <span className="meta-flag">—</span>}</td>
                <td className="meta-schema-check">{f.lexical    ? <span className="meta-flag meta-flag-on">✓</span> : <span className="meta-flag">—</span>}</td>
                <td className="meta-schema-check">{f.semantic   ? <span className="meta-flag meta-flag-on">✓</span> : <span className="meta-flag">—</span>}</td>
                <td>
                  <span className="tag meta-tag-system">system</span>
                </td>
                <td></td>
              </tr>
            ))}
          </tbody>
        </table>

        {metaFields.length === 0 && (
          <div className="stage-config-empty">No metadata fields defined yet.</div>
        )}

        <button type="button" className="btn btn-ghost" style={{ marginTop: 8, fontSize: 12 }} onClick={addField}>
          + Add field
        </button>
      </div>

      {/* ── Save bar ── */}
      <ConfigSaveBar
        status={draft.status}
        isDirty={draft.isDirty}
        onSave={() => { void draft.save() }}
        onDiscard={handleDiscard}
      />
    </div>
  )
}
