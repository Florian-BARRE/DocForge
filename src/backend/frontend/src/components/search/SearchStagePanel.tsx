// ====== Code Summary ======
// SearchStagePanel — hardcoded configuration panel for the four search pipeline stages
// (transform, embed, retrieve, rerank).  Unlike StageConfigPanel it doesn't rely on
// discovery fields; instead it reads and writes directly into configState.pipeline.search.
// Edits accumulate in a local draft buffer (useConfigDraft) and are persisted only when
// the user clicks Save in the ConfigSaveBar at the bottom. The embed stage is read-only.
// This file is a thin dispatcher — each stage section lives under ./panels.

// ====== Third-Party Library Imports ======
import { useState } from 'react'

// ====== Internal Project Imports ======
import type { ConfigState } from '../../api/types'
import { useConfigDraft } from '../../hooks/useConfigDraft'
import { ConfigSaveBar } from '../ui/ConfigSaveBar'

// ====== Local Project Imports ======
import { EmbedSection } from './panels/EmbedSection'
import { RerankSection } from './panels/RerankSection'
import { RetrieveSection } from './panels/RetrieveSection'
import { TransformSection } from './panels/TransformSection'
import { extractSearchCfg } from './panels/searchConfigHelpers'

// ── Types ─────────────────────────────────────────────────────────────────────

/** The four stages supported by this panel. */
type SearchStageId = 'transform' | 'embed' | 'retrieve' | 'rerank'

interface SearchStagePanelProps {
  /** Which stage is being displayed. */
  stageId: SearchStageId
  /** Active collection — used when persisting changes. */
  collectionId: string
  /** Current persisted config state for the collection. */
  configState: ConfigState | null
  /** Called after a successful save so the parent can refresh its copy. */
  onSaved?: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Hardcoded configuration panel for the search pipeline stages.
 *
 * Renders a different form section depending on `stageId`:
 *   - transform  : query_transform.strategy + n_variants (multi_query only)
 *   - embed      : read-only info about the derived embed provider
 *   - retrieve   : full retrieve config (vector mode, fusion, weights, field
 *                  weights, grouping, MMR)
 *   - rerank     : enabled toggle + candidate_k + top_n
 *
 * Edits stage a partial `pipeline.search` patch into the shared draft buffer;
 * nothing is sent to the server until the user clicks Save in the bottom
 * ConfigSaveBar. The patch is wrapped as `{ pipeline: { search: { ... } } }`.
 * The embed stage is read-only and shows no save bar.
 *
 * Args:
 *   stageId:      Which stage to render.
 *   collectionId: Target collection for config persistence.
 *   configState:  Current server-side config (seeds local form state).
 *   onSaved:      Optional callback fired after a successful save.
 */
export function SearchStagePanel({
  stageId,
  collectionId,
  configState,
  onSaved,
}: SearchStagePanelProps) {
  // ── Draft buffer (shared explicit save/discard workflow) ──────────────────
  const draft = useConfigDraft(collectionId, onSaved)

  // Reset nonce: bumped on discard so the active section remounts and re-seeds
  // its local form state from configState (which is unchanged on discard).
  const [resetNonce, setResetNonce] = useState(0)

  /**
   * Stage a partial pipeline.search patch into the draft buffer.
   *
   * The patch covers only the section relevant to the active stage so other
   * search config sections are not accidentally overwritten.
   *
   * Args:
   *   patch: Partial pipeline.search patch to accumulate.
   */
  function handleSave(patch: Record<string, unknown>) {
    draft.stage({ pipeline: { search: patch } })
  }

  /** Discard the draft buffer and force the active section to re-seed. */
  function handleDiscard() {
    draft.discard()
    setResetNonce(n => n + 1)
  }

  const searchCfg = extractSearchCfg(configState)
  // Section key combines stage + nonce so a discard remounts the section,
  // restoring its local state from the (unchanged) persisted config.
  const sectionKey = `${stageId}-${resetNonce}`

  // ── Stage-specific sections ───────────────────────────────────────────────

  return (
    <div className="stage-config-panel">
      {stageId === 'transform' && (
        <TransformSection
          key={sectionKey}
          configState={configState}
          onSave={handleSave}
          searchCfg={searchCfg}
        />
      )}
      {stageId === 'embed' && (
        <EmbedSection configState={configState} />
      )}
      {stageId === 'retrieve' && (
        <RetrieveSection
          key={sectionKey}
          configState={configState}
          searchCfg={searchCfg}
          onSave={handleSave}
        />
      )}
      {stageId === 'rerank' && (
        <RerankSection
          key={sectionKey}
          searchCfg={searchCfg}
          onSave={handleSave}
        />
      )}

      {/* Save bar for all writable stages (embed is read-only). */}
      {stageId !== 'embed' && (
        <ConfigSaveBar
          status={draft.status}
          isDirty={draft.isDirty}
          onSave={() => { void draft.save() }}
          onDiscard={handleDiscard}
          applied={draft.applied}
        />
      )}
    </div>
  )
}
