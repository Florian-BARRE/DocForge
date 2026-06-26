// ====== Code Summary ======
// PipelineFlowGraph — modern horizontal pipeline flow graph replacing PipelineGraph.
// Renders rich StageFlowNode cards connected by SVG StageConnector arrowheads.
// Supports both config mode (provider summary) and trace mode (runtime status).
// Purely presentational: no API calls, all data comes from props.

// ====== Internal Project Imports ======
import type { ConfigState } from '../../api/types'
import { StageConnector } from './StageConnector'
import { StageFlowNode } from './StageFlowNode'
import type { StageDefinition, StageResult } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PipelineFlowGraphProps {
  /** Ordered list of stage definitions to render as nodes. */
  stages: StageDefinition[]
  /** Rendering mode passed down to each StageFlowNode. */
  mode: 'config' | 'trace'
  /** Map of stage id to runtime result (trace mode only). */
  stageResults?: Record<string, StageResult>
  /** Id of the stage currently open in the detail panel, or null for none. */
  activeStageId?: string | null
  /** Called when the user clicks a stage node. */
  onStageClick: (stage: StageDefinition) => void
  /**
   * Current persisted config state for the collection.
   * Used in config mode to derive per-stage provider summaries.
   */
  configState?: ConfigState | null
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Horizontal pipeline flow graph showing all ingestion stages as linked cards.
 *
 * Renders an ordered row of {@link StageFlowNode} components separated by
 * {@link StageConnector} SVG arrowheads.  A mode badge (CONFIG / TRACE) is
 * anchored to the top-right corner of the container.
 *
 * The component is purely presentational — it holds no local state and makes
 * no API calls. All behaviour is driven by the props supplied by the parent.
 *
 * Args:
 *   stages:        Ordered stage definitions to display.
 *   mode:          "config" for pipeline setup, "trace" for post-run inspection.
 *   stageResults:  Per-stage runtime results (trace mode only).
 *   activeStageId: Id of the stage whose detail panel is currently open.
 *   onStageClick:  Callback invoked when the user clicks any stage node.
 *   configState:   Live collection config used for provider summaries.
 */
export function PipelineFlowGraph({
  stages,
  mode,
  stageResults,
  activeStageId,
  onStageClick,
  configState,
}: PipelineFlowGraphProps) {
  return (
    <div className="pipeline-flow-graph">
      {/* Mode badge — top-right corner of the container */}
      <span className="pipeline-flow-badge" aria-label={`Mode: ${mode}`}>
        {mode === 'config' ? 'CONFIG' : 'TRACE'}
      </span>

      {/* Horizontal node row with SVG connectors between stages */}
      <div className="pipeline-flow-nodes">
        {stages.map((stage, index) => (
          <div key={stage.id} style={{ display: 'contents' }}>
            <StageFlowNode
              stage={stage}
              mode={mode}
              result={stageResults?.[stage.id]}
              isActive={activeStageId === stage.id}
              onClick={() => onStageClick(stage)}
              configState={configState}
            />
            {/* Connector after every node except the last */}
            {index < stages.length - 1 && (
              <StageConnector
                highlighted={activeStageId === stages[index + 1]?.id}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
