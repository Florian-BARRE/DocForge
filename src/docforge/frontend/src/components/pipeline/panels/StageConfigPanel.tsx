// ====== Code Summary ======
// Discovery-driven configuration panel for a single pipeline stage.
// Filters the full discovery payload by `stage.fieldPathPrefix` and renders
// all matching fields via DynamicFieldsGroup.  Changes auto-save via
// updateConfig with a 600 ms debounce.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useRef, useState } from 'react'

// ====== Internal Project Imports ======
import { updateConfig } from '../../../api/client'
import type { ConfigState, DynamicField, MetaField } from '../../../api/types'
import { DynamicFieldsGroup } from '../../ui/DynamicFieldsGroup'

// ====== Local Project Imports ======
import type { StageDefinition } from '../types'

// ── Types ────────────────────────────────────────────────────────────────────

interface StageConfigPanelProps {
  /** Stage being configured — drives the field_path prefix filter. */
  stage: StageDefinition
  /** Collection the config belongs to (used when persisting changes). */
  collectionId: string
  /** All dynamic fields from the discovery response — panel filters internally. */
  dynamicFields: DynamicField[]
  /** Current persisted config state for the collection. */
  configState: ConfigState | null
  /** Called after a successful save so the parent can refresh its copy. */
  onSaved?: () => void
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Single-stage configuration panel driven entirely by the discovery payload.
 *
 * No field names are hardcoded here.  The panel filters `dynamicFields` by
 * `stage.fieldPathPrefix`, derives the current value from `configState`, and
 * renders all matching fields via {@link DynamicFieldsGroup}.
 *
 * Changes are debounced (600 ms) and persisted automatically via
 * `updateConfig`.  A save indicator (idle / saving / saved / error) is shown
 * in the panel header.
 *
 * Args:
 *   stage:        Stage definition that owns this panel.
 *   collectionId: Target collection for config persistence.
 *   dynamicFields: Full discovery field list — filtered internally by prefix.
 *   configState:  Current server-side config (used to seed local value state).
 *   onSaved:      Optional callback fired after a successful save.
 */
export function StageConfigPanel({
  stage,
  collectionId,
  dynamicFields,
  configState,
  onSaved,
}: StageConfigPanelProps) {
  // 1. Filter fields that belong to this stage by field_path prefix.
  const stageFields = dynamicFields.filter(f =>
    f.field_path.startsWith(stage.fieldPathPrefix + '.') ||
    f.field_path === stage.fieldPathPrefix
  )

  // 2. Derive initial local value from the stored config state.
  //    The prefix is e.g. "pipeline.ingest" — we navigate into the configState
  //    object along those dot-segments to seed the DynamicFieldsGroup value.
  function extractInitialValue(cfg: ConfigState | null): Record<string, unknown> {
    if (!cfg) return {}
    const parts = stage.fieldPathPrefix.split('.')
    let cursor: unknown = cfg
    for (const part of parts) {
      if (cursor && typeof cursor === 'object') {
        cursor = (cursor as Record<string, unknown>)[part]
      } else {
        return {}
      }
    }
    return (cursor && typeof cursor === 'object') ? (cursor as Record<string, unknown>) : {}
  }

  const [value, setValue] = useState<Record<string, unknown>>(() =>
    extractInitialValue(configState)
  )
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Skip the first save triggered by the initial config load to avoid
  // immediately re-writing unchanged data back to the server.
  const skipNextSave = useRef(true)

  // Re-seed value when the parent loads a different collection or refreshes.
  useEffect(() => {
    setValue(extractInitialValue(configState))
    setSaveState('idle')
    skipNextSave.current = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configState, stage.fieldPathPrefix])

  // 3. Debounced auto-save: fires 600 ms after the last user change.
  //    Builds a nested patch object from the fieldPathPrefix segments so the
  //    backend can apply it as a deep merge.
  const scheduleSave = useCallback((newValue: Record<string, unknown>) => {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    setSaveState('saving')
    saveTimer.current = setTimeout(async () => {
      try {
        // Build nested patch: "pipeline.ingest" → { pipeline: { ingest: newValue } }
        const parts = stage.fieldPathPrefix.split('.')
        const patch = parts.reduceRight<Record<string, unknown>>(
          (acc, key) => ({ [key]: acc }),
          newValue as unknown as Record<string, unknown>,
        )
        await updateConfig(collectionId, patch, `Updated ${stage.label} config`)
        setSaveState('saved')
        onSaved?.()
        setTimeout(() => setSaveState('idle'), 1500)
      } catch {
        setSaveState('error')
        setTimeout(() => setSaveState('idle'), 3000)
      }
    }, 600)
  }, [collectionId, stage.fieldPathPrefix, stage.label, onSaved])

  // 4. Handler for DynamicFieldsGroup changes.
  function handleChange(newValue: Record<string, unknown>) {
    setValue(newValue)
    if (skipNextSave.current) {
      skipNextSave.current = false
      return
    }
    scheduleSave(newValue)
  }

  // 5. Compute the sub-prefix to pass to DynamicFieldsGroup so it strips the
  //    stage prefix and groups by the next path segment (e.g. "ingest.parser"
  //    after stripping "pipeline" becomes "ingest.parser" → group "ingest").
  //    We pass the full fieldPathPrefix as the DynamicFieldsGroup prefix so it
  //    strips it and presents relative paths.
  const dfgPrefix = stage.fieldPathPrefix

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="stage-config-panel">
      {/* Header row: auto-save indicator */}
      <div className="stage-config-save-indicator">
        <SaveIndicator state={saveState} />
      </div>

      {/* S0-specific: collection ingestion conditions (formats, size cap, metadata schema) */}
      {stage.id === 's0' && configState && (
        <IngestionConditions configState={configState} />
      )}

      {stageFields.length === 0 ? (
        stage.id === 's0' ? null : (
          /* Empty state: no discoverable fields for this stage */
          <div className="stage-config-empty">
            No configurable options for this stage.
          </div>
        )
      ) : (
        <DynamicFieldsGroup
          fields={stageFields}
          prefix={dfgPrefix}
          value={value}
          onChange={handleChange}
        />
      )}
    </div>
  )
}

// ── IngestionConditions ───────────────────────────────────────────────────────

/**
 * Displays the collection-level ingestion constraints for the S0 stage:
 * accepted formats, file size cap, metadata schema, and unknown-field policy.
 *
 * Args:
 *   configState: Current collection config containing the conditions to display.
 */
function IngestionConditions({ configState }: { configState: ConfigState }) {
  return (
    <div className="stage-conditions">
      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Accepted formats</div>
        <div className="stage-conditions-chips">
          {configState.supported_formats.map(f => (
            <span key={f} className="tag">{f}</span>
          ))}
        </div>
      </div>

      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Limits</div>
        <div className="stage-panel-row">
          <span className="stage-panel-label">Max file size</span>
          <span className="stage-panel-value mono">{formatBytes(configState.max_file_size_bytes)}</span>
        </div>
        <div className="stage-panel-row">
          <span className="stage-panel-label">Unknown fields</span>
          <span className="stage-panel-value">{configState.unknown_field_policy}</span>
        </div>
      </div>

      <div className="stage-conditions-section">
        <div className="stage-conditions-title">Metadata schema</div>
        {configState.metadata_fields.length === 0 ? (
          <div className="stage-config-empty">No metadata fields defined.</div>
        ) : (
          <table className="stage-conditions-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Type</th>
                <th>Req.</th>
                <th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {configState.metadata_fields.map((f: MetaField) => (
                <tr key={f.field_name} className={f.is_system ? 'stage-conditions-row-system' : ''}>
                  <td className="mono" style={{ fontSize: 11 }}>{f.field_name}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{f.field_type}</td>
                  <td style={{ color: f.required ? 'var(--s-done)' : 'var(--text-dim)' }}>
                    {f.required ? '✓' : '—'}
                  </td>
                  <td style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                    {[
                      f.filterable && 'filter',
                      f.lexical    && 'lex',
                      f.semantic   && 'sem',
                      f.is_system  && 'sys',
                    ].filter(Boolean).join(' · ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Formats a byte count into a human-readable string (KB / MB / GB).
 *
 * Args:
 *   bytes: Number of bytes to format.
 *
 * Returns:
 *   Formatted string, e.g. "50.0 MB".
 */
function formatBytes(bytes: number): string {
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`
  if (bytes >= 1_048_576)     return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1_024)         return `${(bytes / 1_024).toFixed(1)} KB`
  return `${bytes} B`
}

// ── SaveIndicator ─────────────────────────────────────────────────────────────

/**
 * Inline transient feedback label for auto-save state.
 *
 * Returns null when state is 'idle' so the indicator row collapses cleanly.
 *
 * Args:
 *   state: Current save lifecycle state.
 */
function SaveIndicator({ state }: { state: SaveState }) {
  if (state === 'idle') return null
  const meta: Record<string, { text: string; color: string }> = {
    saving: { text: 'saving…', color: 'var(--text-dim)' },
    saved:  { text: '✓ saved', color: 'var(--s-done)' },
    error:  { text: '✗ error', color: 'var(--s-error)' },
  }
  const m = meta[state]
  return (
    <span style={{ color: m.color }}>
      {m.text}
    </span>
  )
}
