// ====== Code Summary ======
// Orchestrator for the Pipeline tab.
// Config mode (activeDocId null): fetches discovery fields + config state, renders
// PipelineGraph in "config" mode, shows StageConfigPanel inline below the graph on click.
// Trace mode (activeDocId non-null): fetches the document, passes stageResults derived
// from the document to PipelineGraph in "trace" mode, shows trace panels inline below.
//
// Unsaved-changes guard (config mode only): when a stage draft is dirty and the user
// clicks a different stage or closes the panel, a ConfirmDialog intercepts the action
// and asks for confirmation before discarding the unsaved edits.

// ====== Standard Library Imports ======
// (none)

// ====== Third-Party Library Imports ======
import { useCallback, useEffect, useState } from 'react'

// ====== Internal Project Imports ======
import { getConfigState, getDiscovery, getDocument } from '../../api/client'
import type { ConfigState, DiscoveryResponse, Document, DynamicField } from '../../api/types'
import { ConfirmDialog } from '../ui/ConfirmDialog'

// ====== Local Project Imports ======
import { ConfigHistoryPanel } from './ConfigHistoryPanel'
import { PipelineCanvas } from './PipelineCanvas'
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
  /**
   * When false, config save bars and rollback buttons are replaced by a
   * read-only notice.  Derived from the current user's collection grant.
   */
  canWrite?: boolean
}

/**
 * Pending navigation action held while the discard-changes dialog is open.
 * `nextStage === null` means the user clicked "close panel"; a StageDefinition
 * means they clicked a different stage node.
 */
interface PendingNavigation {
  nextStage: StageDefinition | null
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
 *   {@link PipelineCanvas} in "config" mode, and opens an inline panel below
 *   containing {@link StageConfigPanel} when the user clicks a stage node.
 *   An unsaved-changes guard (ConfirmDialog) intercepts stage switches and
 *   panel closes when the active draft is dirty.
 *
 * Trace mode (activeDocId !== null):
 *   Fetches the selected document, derives per-stage results, renders
 *   {@link PipelineCanvas} in "trace" mode with colored nodes, and opens a
 *   panel with the appropriate trace panel for the clicked stage.
 *
 * Args:
 *   collectionId:   Collection being configured or traced.
 *   activeDocId:    Document selected for trace mode; null for config mode.
 *   onRequestTrace: Callback to exit trace mode (called with null).
 *   canWrite:       When false, config panels are read-only.
 */
export function PipelineTab({
  collectionId,
  activeDocId,
  onRequestTrace,
  canWrite = true,
}: PipelineTabProps) {
  // 1. Discovery fields — all DynamicField objects for this collection.
  const [dynamicFields, setDynamicFields] = useState<DynamicField[]>([])

  // 1b. Full discovery response — passed to StageConfigPanel for config_tree path.
  const [discovery, setDiscovery] = useState<DiscoveryResponse | null>(null)

  // 2. Current persisted config state.
  const [configState, setConfigState] = useState<ConfigState | null>(null)

  // 3. The stage node currently selected (shows inline panel below the graph).
  const [activeStage, setActiveStage] = useState<StageDefinition | null>(null)

  // 3a. Dirty-draft guard: StageConfigPanel signals its isDirty state up via
  //     onDirtyChange.  When true, stage switches and panel closes are intercepted.
  const [isDraftDirty, setIsDraftDirty] = useState(false)

  // Holds the pending navigation intent while the discard dialog is open.
  // null entry = "close panel"; StageDefinition entry = "switch to that stage".
  const [pendingNav, setPendingNav] = useState<PendingNavigation | null>(null)

  // 4. Document fetched for trace mode (null when in config mode or loading).
  const [traceDoc, setTraceDoc] = useState<Document | null>(null)

  // 5. Whether the inline config-history panel is visible (config mode only).
  const [showHistory, setShowHistory] = useState(false)

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
        // Store the full discovery response so StageConfigPanel can use config_tree.
        setDiscovery(discoveryResp)
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

  // 10. Reset isDraftDirty whenever the active stage changes (new stage mounts a
  //     fresh draft; closing the panel unmounts StageConfigPanel entirely).
  useEffect(() => {
    setIsDraftDirty(false)
  }, [activeStage?.id])

  // ── Navigation helpers ─────────────────────────────────────────────────────

  /**
   * Attempt to navigate to nextStage (null = close panel).
   *
   * In config mode, if the current draft is dirty and the navigation would
   * move away from the open stage, the action is held in pendingNav and a
   * ConfirmDialog is shown instead of navigating immediately.
   *
   * Args:
   *   nextStage: The target stage to open, or null to close the panel.
   */
  function requestNavigation(nextStage: StageDefinition | null): void {
    const isSameStage = nextStage?.id === activeStage?.id
    // Guard only applies in config mode when the panel is open and the draft
    // is dirty, AND the user is navigating away (not re-clicking the same stage).
    if (mode === 'config' && isDraftDirty && activeStage !== null && !isSameStage) {
      setPendingNav({ nextStage })
      return
    }
    // No guard needed (or same-stage toggle) — navigate directly.
    setActiveStage(nextStage?.id === activeStage?.id ? null : nextStage)
  }

  /** Called when the user clicks a stage node on the canvas. */
  function handleStageClick(stage: StageDefinition): void {
    requestNavigation(stage)
  }

  /** Called when the user clicks the × close button on the inline panel header. */
  function handleClosePanel(): void {
    requestNavigation(null)
  }

  /** User confirmed they want to discard the unsaved draft and navigate. */
  function handleDiscardConfirm(): void {
    const next = pendingNav?.nextStage ?? null
    setPendingNav(null)
    setActiveStage(next)
  }

  /** User cancelled — keep the panel open with the current draft intact. */
  function handleDiscardCancel(): void {
    setPendingNav(null)
  }

  // 11. Derive stage results only when in trace mode and the document is loaded.
  const stageResults =
    mode === 'trace' && traceDoc ? deriveStageResults(traceDoc) : undefined

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

      {/* ── Config version + reindex indicator + history toggle ── */}
      {mode === 'config' && configState && (
        <>
          <div className="pipeline-version-bar">
            <span className="mono">pipeline_version: {configState.pipeline_version}</span>
            {configState.needs_reindex && (
              <span
                className="tag doc-stale-badge"
                title="Some documents were ingested with an older pipeline configuration."
              >
                Reindex required
              </span>
            )}
            <button
              type="button"
              className="btn btn-ghost pipeline-history-toggle"
              onClick={() => setShowHistory(prev => !prev)}
            >
              {showHistory ? 'Hide history' : 'History'}
            </button>
          </div>

          {/* Inline config history with rollback, toggled from the bar above.
              canWrite gates the rollback button inside the panel. */}
          {showHistory && (
            <ConfigHistoryPanel
              collectionId={collectionId}
              onRolledBack={handleSaved}
              canWrite={canWrite}
            />
          )}
        </>
      )}

      {/* ── Pipeline canvas (react-flow) ── */}
      <PipelineCanvas
        stages={INGESTION_STAGES}
        mode={mode}
        stageResults={stageResults}
        activeStageId={activeStage?.id ?? null}
        onStageClick={handleStageClick}
        configState={configState}
      />

      {/* ── Inline config / trace panel ── */}
      <div className="pipeline-inline-panel">
        {!activeStage ? (
          <div className="pipeline-inline-panel-empty">
            {mode === 'config'
              ? 'Click a stage to view its configuration'
              : 'Click a stage to inspect its trace'}
          </div>
        ) : (
          <>
            <div className="pipeline-inline-panel-header">
              <span className="pipeline-inline-panel-title">
                {activeStage.label}{mode === 'trace' ? ' — Trace' : ' Configuration'}
              </span>
              <button
                type="button"
                className="btn-icon"
                onClick={handleClosePanel}
                aria-label="Close panel"
              >
                ×
              </button>
            </div>
            <div className="pipeline-inline-panel-body">
              {mode === 'config' && (
                <StageConfigPanel
                  stage={activeStage}
                  collectionId={collectionId}
                  dynamicFields={dynamicFields}
                  discovery={discovery}
                  configState={configState}
                  onSaved={handleSaved}
                  canWrite={canWrite}
                  onDirtyChange={setIsDraftDirty}
                />
              )}
              {mode === 'trace' && traceDoc && stageResults &&
                buildTracePanel(activeStage, traceDoc, collectionId, stageResults)
              }
            </div>
          </>
        )}
      </div>

      {/* ── Unsaved-changes guard dialog ── */}
      <ConfirmDialog
        open={pendingNav !== null}
        title="Unsaved changes"
        message={
          `Discard unsaved changes to ${activeStage?.label ?? 'this stage'}? ` +
          'Your edits will be lost.'
        }
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        danger
        onConfirm={handleDiscardConfirm}
        onCancel={handleDiscardCancel}
      />
    </div>
  )
}
