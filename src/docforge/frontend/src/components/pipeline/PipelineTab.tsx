// ====== Code Summary ======
// Orchestrator for the Pipeline tab.
// Config mode (activeDocId null): fetches discovery fields + config state, renders
// PipelineGraph in "config" mode, opens StageConfigPanel in a SlidePanel on click.
// Trace mode (activeDocId non-null): fetches the document, passes stageResults derived
// from the document to PipelineGraph in "trace" mode, opens trace panels on click.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getConfigState, getDiscovery, getDocument } from '../../api/client'
import type { ConfigState, Document, DynamicField } from '../../api/types'
import { SlidePanel } from '../layout/SlidePanel'

// ====== Local Project Imports ======
import { PipelineGraph } from './PipelineGraph'
import { S0Panel } from './panels/S0Panel'
import { S1Panel } from './panels/S1Panel'
import { S2Panel } from './panels/S2Panel'
import { S45Panel } from './panels/S45Panel'
import { S6Panel } from './panels/S6Panel'
import { StageConfigPanel } from './panels/StageConfigPanel'
import { INGESTION_STAGES } from './stages'
import type { StageDefinition, StageResult, StageStatus } from './types'

// ── Types ────────────────────────────────────────────────────────────────────

interface PipelineTabProps {
  /** Collection to configure or trace. */
  collectionId: string
  /**
   * When non-null, a document is selected and the tab shows trace mode.
   * When null, the tab is in config mode.
   */
  activeDocId: string | null
  /** Callback used to close trace mode by passing null. */
  onRequestTrace?: (docId: string | null) => void
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Derive a StageStatus from a raw document status string.
 *
 * The mapping reflects the pipeline lifecycle: a "done" document has passed
 * every stage, "running" means at least one stage is active, "error" means a
 * stage failed, and anything else is treated as "pending".
 *
 * Args:
 *   docStatus: Raw status string from the document record.
 *
 * Returns:
 *   A StageStatus value compatible with StageResult.
 */
function docStatusToStageStatus(docStatus: string): StageStatus {
  switch (docStatus) {
    case 'done':    return 'done'
    case 'running': return 'running'
    case 'error':   return 'error'
    default:        return 'pending'
  }
}

/**
 * Build a StageResult map from a Document record.
 *
 * The backend does not currently expose per-stage timing in the document
 * endpoint, so we derive a coarse status from doc.status.  When doc.indexed
 * is false on a completed document we mark S6 as "skipped" to reflect that
 * the vector store was not reachable during ingestion.
 *
 * Args:
 *   doc: Fully hydrated document record returned by getDocument.
 *
 * Returns:
 *   A map of stage id to StageResult for every INGESTION_STAGES entry.
 */
function deriveStageResults(doc: Document): Record<string, StageResult> {
  const globalStatus = docStatusToStageStatus(doc.status)

  // S6 can be "done" (chunks exist) or "pending" (vector store unreachable)
  // even when the overall doc status is "done".
  const s6Status: StageStatus =
    doc.status === 'done' && doc.indexed ? 'done'
    : doc.status === 'done' && !doc.indexed ? 'skipped'
    : globalStatus

  return {
    s0: {
      status: 'done',  // S0 is always done if we have a Document record.
      metric: `${doc.format.toUpperCase()} · ${(doc.file_size / 1024).toFixed(1)} KB`,
    },
    s1: {
      status: globalStatus,
      metric: [
        doc.block_count != null ? `${doc.block_count} blocks` : null,
        doc.page_count  != null ? `${doc.page_count} pp`      : null,
      ].filter(Boolean).join(' · ') || undefined,
    },
    s2: {
      // S2 is opt-in; we can't tell from the document record alone whether it
      // was skipped or ran — use the global status as the best approximation.
      status: globalStatus,
    },
    s4: {
      status: globalStatus,
      metric: doc.chunk_count != null ? `${doc.chunk_count} chunks` : undefined,
    },
    s5: {
      status: globalStatus,
    },
    s6: {
      status: s6Status,
      metric: doc.indexed && doc.chunk_count != null
        ? `${doc.chunk_count} indexed`
        : undefined,
    },
  }
}

/**
 * Build the trace panel JSX for a given stage.
 *
 * Returns the appropriate panel component based on the stage id, or null for
 * stages that have no dedicated trace panel yet.
 *
 * Args:
 *   stage:        The stage definition that was clicked.
 *   doc:          The fully hydrated document record.
 *   collectionId: Collection identifier forwarded to sub-components.
 *   results:      Derived stage result map from deriveStageResults.
 */
function buildTracePanel(
  stage: StageDefinition,
  doc: Document,
  collectionId: string,
  results: Record<string, StageResult>,
): JSX.Element | null {
  const result = results[stage.id] ?? { status: 'pending' as StageStatus }

  switch (stage.id) {
    case 's0':
      return <S0Panel stageResult={result} doc={doc} />
    case 's1':
      return <S1Panel stageResult={result} collectionId={collectionId} doc={doc} />
    case 's2':
      return <S2Panel stageResult={result} doc={doc} />
    case 's4':
    case 's5':
      return <S45Panel stageResult={result} collectionId={collectionId} doc={doc} />
    case 's6':
      return <S6Panel stageResult={result} doc={doc} />
    default:
      return null
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Pipeline tab — unified config and trace mode orchestrator.
 *
 * Config mode (activeDocId === null):
 *   Fetches discovery fields and the current config state on mount, renders
 *   {@link PipelineGraph} in "config" mode, and opens a {@link SlidePanel}
 *   containing {@link StageConfigPanel} when the user clicks a stage node.
 *
 * Trace mode (activeDocId !== null):
 *   Fetches the selected document, derives per-stage results, renders
 *   {@link PipelineGraph} in "trace" mode with colored nodes, and opens a
 *   SlidePanel with the appropriate trace panel for the clicked stage.
 *   A trace banner at the top shows the document name with a close button.
 *
 * Args:
 *   collectionId:   Collection being configured or traced.
 *   activeDocId:    Document selected for trace mode; null for config mode.
 *   onRequestTrace: Callback to exit trace mode (called with null).
 */
export function PipelineTab({
  collectionId,
  activeDocId,
  onRequestTrace,
}: PipelineTabProps) {
  // 1. Discovery fields — all DynamicField objects for this collection.
  const [dynamicFields, setDynamicFields] = useState<DynamicField[]>([])

  // 2. Current persisted config state.
  const [configState, setConfigState] = useState<ConfigState | null>(null)

  // 3. The stage node currently open in the SlidePanel.
  const [activeStage, setActiveStage] = useState<StageDefinition | null>(null)

  // 4. Controls whether the SlidePanel is visible.
  const [slidePanelOpen, setSlidePanelOpen] = useState(false)

  // 5. Document fetched for trace mode (null when in config mode or loading).
  const [traceDoc, setTraceDoc] = useState<Document | null>(null)

  // 6. Determine mode from the presence of activeDocId.
  const mode: 'config' | 'trace' = activeDocId ? 'trace' : 'config'

  // 7. Fetch discovery + config state in parallel whenever the collection changes.
  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const [discoveryResp, cfgState] = await Promise.all([
          getDiscovery(collectionId),
          getConfigState(collectionId),
        ])
        if (cancelled) return

        // Flatten all dynamic fields from all endpoints into a single list.
        const allFields: DynamicField[] = discoveryResp.endpoints.flatMap(
          e => e.dynamic_fields ?? []
        )
        setDynamicFields(allFields)
        setConfigState(cfgState)
      } catch {
        // Non-fatal: the panel will render in empty state.
      }
    }

    load()
    return () => { cancelled = true }
  }, [collectionId])

  // 8. Fetch the trace document whenever activeDocId changes.
  useEffect(() => {
    if (!activeDocId) {
      setTraceDoc(null)
      return
    }

    // Capture docId now — TypeScript cannot narrow activeDocId inside the async closure.
    const docId = activeDocId
    let cancelled = false

    async function fetchDoc() {
      try {
        const doc = await getDocument(collectionId, docId)
        if (!cancelled) setTraceDoc(doc)
      } catch {
        // Non-fatal: trace panels will show empty / pending state.
        if (!cancelled) setTraceDoc(null)
      }
    }

    fetchDoc()
    return () => { cancelled = true }
  }, [collectionId, activeDocId])

  // 9. Refresh config state after a successful save in StageConfigPanel.
  const handleSaved = useCallback(async () => {
    try {
      const updated = await getConfigState(collectionId)
      setConfigState(updated)
    } catch {
      // Silent — the panel already showed a success indicator.
    }
  }, [collectionId])

  // 10. Stage node click: select the stage and open the panel.
  function handleStageClick(stage: StageDefinition) {
    setActiveStage(stage)
    setSlidePanelOpen(true)
  }

  // 11. Derive stage results only when in trace mode and the document is loaded.
  const stageResults =
    mode === 'trace' && traceDoc ? deriveStageResults(traceDoc) : undefined

  // 12. Build the SlidePanel title based on mode.
  const slidePanelTitle = activeStage
    ? mode === 'trace'
      ? `${activeStage.label} — Trace`
      : `${activeStage.label} Configuration`
    : ''

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="pipeline-tab">
      {/* ── Trace banner ── */}
      {mode === 'trace' && traceDoc && (
        <div className="pipeline-trace-bar">
          <span className="pipeline-trace-label">Tracing:</span>
          <span className="pipeline-trace-filename">{traceDoc.filename}</span>
          <button
            type="button"
            className="pipeline-trace-close btn btn-ghost"
            onClick={() => onRequestTrace?.(null)}
            aria-label="Close trace mode"
          >
            ×
          </button>
        </div>
      )}

      {/* ── Pipeline graph ── */}
      <PipelineGraph
        stages={INGESTION_STAGES}
        mode={mode}
        stageResults={stageResults}
        activeStageId={activeStage?.id ?? null}
        onStageClick={handleStageClick}
      />

      {/* ── Hint — only visible in config mode ── */}
      {mode === 'config' && (
        <p className="pipeline-tab-hint">
          Drop a file in the Documents tab to trace the pipeline
        </p>
      )}

      {/* ── Slide panel ── */}
      <SlidePanel
        isOpen={slidePanelOpen}
        title={slidePanelTitle}
        onClose={() => setSlidePanelOpen(false)}
      >
        {activeStage && mode === 'config' && (
          <StageConfigPanel
            stage={activeStage}
            collectionId={collectionId}
            dynamicFields={dynamicFields}
            configState={configState}
            onSaved={handleSaved}
          />
        )}

        {activeStage && mode === 'trace' && traceDoc && stageResults && (
          buildTracePanel(activeStage, traceDoc, collectionId, stageResults)
        )}
      </SlidePanel>
    </div>
  )
}
