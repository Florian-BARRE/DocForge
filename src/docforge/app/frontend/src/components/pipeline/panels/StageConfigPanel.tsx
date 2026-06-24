// ====== Code Summary ======
// Discovery-driven configuration panel for a single pipeline stage.
// Filters the full discovery payload by `stage.fieldPathPrefix` and renders
// all matching fields via DynamicFieldsGroup. Edits accumulate in a local draft
// buffer (useConfigDraft) and are persisted only when the user clicks Save in the
// ConfigSaveBar at the bottom. The S0 case delegates to IngestionConditionsPanel,
// which owns its own draft buffer and save bar.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState, DynamicField } from '../../../api/types'
import { useConfigDraft } from '../../../hooks/useConfigDraft'
import { ConfigSaveBar } from '../../ui/ConfigSaveBar'
import { DynamicFieldsGroup } from '../../ui/DynamicFieldsGroup'

// ====== Local Project Imports ======
import type { StageDefinition } from '../types'
import { IngestionConditionsPanel } from './IngestionConditionsPanel'

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
  /**
   * When false, all pickers are rendered in display-only mode and the save bar
   * is replaced by a read-only notice.  Passed through to IngestionConditionsPanel.
   */
  canWrite?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Single-stage configuration panel driven entirely by the discovery payload.
 *
 * No field names are hardcoded here. The panel filters `dynamicFields` by
 * `stage.fieldPathPrefix`, derives the current value from `configState`, and
 * renders all matching fields via {@link DynamicFieldsGroup}.
 *
 * Edits stage a nested patch (built from the fieldPathPrefix segments) into the
 * shared draft buffer; nothing is sent to the server until the user clicks Save
 * in the bottom ConfigSaveBar. For the S0 stage the editable conditions live in
 * the nested {@link IngestionConditionsPanel}, which owns its own draft + save
 * bar — so no save bar is rendered at this level for S0.
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
  canWrite = true,
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

  // 3. Draft buffer (shared explicit save/discard workflow).
  const draft = useConfigDraft(collectionId, onSaved)

  const [value, setValue] = useState<Record<string, unknown>>(() =>
    extractInitialValue(configState)
  )

  // Reset nonce: bumped when configState/prefix changes OR on local discard, so
  // the seed effect below can restore local form state from the persisted config.
  const [resetNonce, setResetNonce] = useState(0)

  // Bump the nonce whenever the parent provides a fresh config or the stage changes.
  useEffect(() => {
    setResetNonce(n => n + 1)
  }, [configState, stage.fieldPathPrefix])

  // Re-seed local value on mount, parent refresh, stage change, or discard.
  useEffect(() => {
    setValue(extractInitialValue(configState))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetNonce])

  /** Discard the draft buffer and re-seed the local value from configState. */
  function handleDiscard() {
    draft.discard()
    setResetNonce(n => n + 1)
  }

  // 4. Handler for DynamicFieldsGroup changes — stages a nested patch.
  //    Builds "pipeline.ingest" → { pipeline: { ingest: newValue } } so the
  //    backend can apply it as a deep merge.
  function handleChange(newValue: Record<string, unknown>) {
    setValue(newValue)
    const parts = stage.fieldPathPrefix.split('.')
    const patch = parts.reduceRight<Record<string, unknown>>(
      (acc, key) => ({ [key]: acc }),
      newValue,
    )
    draft.stage(patch)
  }

  // 5. Pass the full fieldPathPrefix as the DynamicFieldsGroup prefix so it
  //    strips it and presents relative paths.
  const dfgPrefix = stage.fieldPathPrefix

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="stage-config-panel">
      {/* S0-specific: editable collection ingestion conditions (formats, size cap, metadata schema).
          IngestionConditionsPanel owns its own draft buffer + ConfigSaveBar. */}
      {stage.id === 's0' && configState && (
        <IngestionConditionsPanel
          configState={configState}
          collectionId={collectionId}
          onSaved={onSaved}
          canWrite={canWrite}
        />
      )}

      {stageFields.length === 0 ? (
        stage.id === 's0' ? null : (
          /* Empty state: no discoverable fields for this stage */
          <div className="stage-config-empty">
            No configurable options for this stage.
          </div>
        )
      ) : (
        <>
          <DynamicFieldsGroup
            fields={stageFields}
            prefix={dfgPrefix}
            value={value}
            onChange={handleChange}
          />
          {/* Save bar only for non-S0 stages; S0 uses the nested panel's bar.
              Read-only users see a notice instead of the save/discard actions. */}
          {stage.id !== 's0' && (
            canWrite ? (
              <ConfigSaveBar
                status={draft.status}
                isDirty={draft.isDirty}
                onSave={() => { void draft.save() }}
                onDiscard={handleDiscard}
                applied={draft.applied}
              />
            ) : (
              <div className="info-banner" style={{ marginTop: 8 }}>
                <span className="info-icon">ℹ</span>
                <span>Read-only — you do not have write access to this collection.</span>
              </div>
            )
          )}
        </>
      )}
    </div>
  )
}
