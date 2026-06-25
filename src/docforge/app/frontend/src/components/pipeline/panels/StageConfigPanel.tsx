// ====== Code Summary ======
// Discovery-driven configuration panel for a single pipeline stage.
//
// Two rendering paths (graceful upgrade):
//   1. config_tree path (preferred): finds the ConfigNode subtree rooted at
//      stage.fieldPathPrefix inside the update_config endpoint's config_tree,
//      then renders it via RecursiveFieldRenderer.  Handles gates, nested unions
//      (semantic.embed), chains, and all search stages through the same code path.
//   2. Legacy flat path (fallback): filters dynamic_fields by fieldPathPrefix and
//      renders via DynamicFieldsGroup (kept while config_tree is absent).
//
// Either way, edits accumulate in useConfigDraft and are persisted only on Save.
// S0 delegates ingestion conditions to IngestionConditionsPanel (own draft + bar).

// ====== Third-Party Library Imports ======
import { useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigNode, ConfigState, DiscoveryResponse, DynamicField } from '../../../api/types'
import { useConfigDraft } from '../../../hooks/useConfigDraft'
import { ConfigSaveBar } from '../../ui/ConfigSaveBar'
import { DynamicFieldsGroup } from '../../ui/DynamicFieldsGroup'
import { RecursiveFieldRenderer } from '../../ui/RecursiveFieldRenderer'
import { readPath, setPath } from '../../ui/pathUtils'

// ====== Local Project Imports ======
import type { StageDefinition } from '../types'
import { IngestionConditionsPanel } from './IngestionConditionsPanel'

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Depth-first search for a ConfigNode whose path equals targetPath.
 * Searches children and choice.params to cover the whole tree.
 *
 * Args:
 *   node:       Root node to search from.
 *   targetPath: Exact absolute path to find.
 *
 * Returns:
 *   ConfigNode | null: Matching node, or null if not found.
 */
function findSubtree(node: ConfigNode, targetPath: string): ConfigNode | null {
  if (node.path === targetPath) return node
  for (const child of node.children ?? []) {
    const found = findSubtree(child, targetPath)
    if (found) return found
  }
  for (const choice of node.choices ?? []) {
    for (const param of choice.params ?? []) {
      const found = findSubtree(param, targetPath)
      if (found) return found
    }
  }
  return null
}

/**
 * Extract the config_tree from the update_config endpoint in a discovery response.
 *
 * Args:
 *   discovery: Discovery response, or null.
 *
 * Returns:
 *   ConfigNode | null: Root of the update_config config_tree, or null.
 */
function getUpdateConfigTree(discovery: DiscoveryResponse | null): ConfigNode | null {
  if (!discovery) return null
  const ep = discovery.endpoints.find(e => e.route_name === 'update_config')
  return ep?.config_tree ?? null
}

/**
 * Map a stage fieldPathPrefix to the backend config_tree absolute path.
 * The backend roots the update_config tree at `patch.pipeline`, so
 * "pipeline.search.retrieve" -> "patch.pipeline.search.retrieve".
 *
 * Args:
 *   fieldPathPrefix: Stage prefix.
 *
 * Returns:
 *   string: Corresponding absolute path in the config_tree.
 */
function treePathFor(fieldPathPrefix: string): string {
  return `patch.${fieldPathPrefix}`
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface StageConfigPanelProps {
  /** Stage being configured — drives the field_path prefix filter. */
  stage: StageDefinition
  /** Collection the config belongs to (used when persisting changes). */
  collectionId: string
  /** All dynamic fields from the discovery response — legacy path fallback. */
  dynamicFields: DynamicField[]
  /** Full discovery response — provides the config_tree for the preferred path. */
  discovery?: DiscoveryResponse | null
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
 * Single-stage configuration panel driven by the discovery config_tree.
 *
 * Navigates the update_config config_tree to the subtree matching
 * stage.fieldPathPrefix, then renders all descendant nodes via
 * RecursiveFieldRenderer. Falls back to the legacy DynamicFieldsGroup
 * when no config_tree is available.
 *
 * Args:
 *   stage:        Stage definition that owns this panel.
 *   collectionId: Target collection for config persistence.
 *   dynamicFields: Full discovery field list (legacy fallback only).
 *   discovery:    Full discovery response (provides config_tree).
 *   configState:  Current server-side config (seeds the local draft value).
 *   onSaved:      Optional callback fired after a successful save.
 *   canWrite:     Gate: false renders a read-only notice instead of the save bar.
 */
export function StageConfigPanel({
  stage,
  collectionId,
  dynamicFields,
  discovery = null,
  configState,
  onSaved,
  canWrite = true,
}: StageConfigPanelProps) {
  // 1. Try the config_tree path (preferred).
  const configTree = getUpdateConfigTree(discovery)
  const treePath = treePathFor(stage.fieldPathPrefix)
  const subtree = configTree ? findSubtree(configTree, treePath) : null

  // 2. Legacy fallback: filter flat dynamic fields by prefix.
  const stageFields = subtree
    ? []
    : dynamicFields.filter(f =>
        f.field_path.startsWith(stage.fieldPathPrefix + '.') ||
        f.field_path === stage.fieldPathPrefix
      )

  // 3. Derive initial local value from the stored config state.
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

  // 4. Draft buffer — shared explicit save/discard workflow.
  const draft = useConfigDraft(collectionId, onSaved)

  const [value, setValue] = useState<Record<string, unknown>>(() =>
    extractInitialValue(configState)
  )

  // Nonce bumped when configState/prefix changes OR on local discard.
  const [resetNonce, setResetNonce] = useState(0)

  useEffect(() => {
    setResetNonce(n => n + 1)
  }, [configState, stage.fieldPathPrefix])

  useEffect(() => {
    setValue(extractInitialValue(configState))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetNonce])

  function handleDiscard() {
    draft.discard()
    setResetNonce(n => n + 1)
  }

  // 5. Handler for value changes — stages a nested patch from the prefix.
  //    "pipeline.embed" -> { pipeline: { embed: newValue } }
  function handleChange(newValue: Record<string, unknown>) {
    setValue(newValue)
    const parts = stage.fieldPathPrefix.split('.')
    const patch = parts.reduceRight<Record<string, unknown>>(
      (acc, key) => ({ [key]: acc }),
      newValue,
    )
    draft.stage(patch)
  }

  // 6. RecursiveFieldRenderer accessors.
  //    absPath = "patch.pipeline.embed.gate.min_score"
  //    Strip the tree prefix ("patch.pipeline.embed.") to get the relative key
  //    within the local value object rooted at the stage subtree.
  const prefixDot = treePath + '.'

  function readValue(absPath: string): unknown {
    const rel = absPath.startsWith(prefixDot) ? absPath.slice(prefixDot.length) : absPath
    return readPath(value, rel)
  }

  function writeValue(absPath: string, v: unknown) {
    const rel = absPath.startsWith(prefixDot) ? absPath.slice(prefixDot.length) : absPath
    handleChange(setPath(value, rel, v))
  }

  // ── Render ──────────────────────────────────────────────────────────────────

  const hasContent = subtree
    ? (subtree.children ?? []).length > 0 || (subtree.choices ?? []).length > 0
    : stageFields.length > 0

  return (
    <div className="stage-config-panel">
      {/* S0-specific: ingestion conditions have their own draft buffer + save bar. */}
      {stage.id === 's0' && configState && (
        <IngestionConditionsPanel
          configState={configState}
          collectionId={collectionId}
          onSaved={onSaved}
          canWrite={canWrite}
        />
      )}

      {!hasContent ? (
        stage.id === 's0' ? null : (
          <div className="stage-config-empty">
            No configurable options for this stage.
          </div>
        )
      ) : (
        <>
          {/* Preferred path: config_tree rendered by RecursiveFieldRenderer */}
          {subtree && (
            <RecursiveFieldRenderer
              nodes={
                // Object nodes expose their children; chain/union are rendered as-is.
                subtree.kind === 'object'
                  ? (subtree.children ?? [])
                  : [subtree]
              }
              readValue={readValue}
              writeValue={writeValue}
            />
          )}

          {/* Legacy path: flat dynamic fields via DynamicFieldsGroup */}
          {!subtree && stageFields.length > 0 && (
            <DynamicFieldsGroup
              fields={stageFields}
              prefix={stage.fieldPathPrefix}
              value={value}
              onChange={handleChange}
              discovery={discovery ?? undefined}
            />
          )}

          {/* Save bar — S0 has its own bar inside IngestionConditionsPanel. */}
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
