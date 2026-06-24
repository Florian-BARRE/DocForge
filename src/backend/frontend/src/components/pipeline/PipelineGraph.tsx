// ====== Code Summary ======
// Horizontal pipeline graph — renders an ordered row of StageNode components
// connected by CSS arrows. Supports config and trace display modes.
// Purely presentational: no API calls, all data supplied via props.

// ====== Local Project Imports ======
import { StageNode } from './StageNode'
import type { StageDefinition, StageResult } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PipelineGraphProps {
  /** Ordered list of stage definitions to render as nodes. */
  stages: StageDefinition[]
  /** Rendering mode passed down to each StageNode. */
  mode: 'config' | 'trace'
  /** Map of stage id → runtime result, used in trace mode. */
  stageResults?: Record<string, StageResult>
  /** Id of the stage currently open in the SlidePanel, or null for none. */
  activeStageId?: string | null
  /** Called when the user clicks a stage node. */
  onStageClick: (stage: StageDefinition) => void
}

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Horizontal pipeline graph showing all stages as linked nodes.
 *
 * Renders a row of {@link StageNode} components separated by CSS arrows.
 * A mode badge ("CONFIG" or "TRACE") is positioned in the top-right corner
 * of the container.
 *
 * The component is purely presentational — it holds no local state and makes
 * no API calls. All behaviour is driven by the props supplied by the parent.
 *
 * Args:
 *   stages:        Ordered stage definitions to display.
 *   mode:          "config" for pipeline setup, "trace" for live/post-run inspection.
 *   stageResults:  Map of stage id to runtime results (trace mode only).
 *   activeStageId: Id of the stage currently selected in a SlidePanel.
 *   onStageClick:  Callback invoked when the user clicks any stage node.
 */
export function PipelineGraph({
  stages,
  mode,
  stageResults,
  activeStageId,
  onStageClick,
}: PipelineGraphProps) {
  return (
    <div className="pipeline-graph">
      {/* Mode badge — top-right corner */}
      <span className="pipeline-graph-badge">{mode === 'config' ? 'CONFIG' : 'TRACE'}</span>

      {/* Node row with arrows between consecutive stages */}
      <div className="pipeline-graph-nodes">
        {stages.map((stage, index) => (
          <div key={stage.id} style={{ display: 'contents' }}>
            <StageNode
              stage={stage}
              mode={mode}
              result={stageResults?.[stage.id]}
              isActive={activeStageId === stage.id}
              onClick={() => onStageClick(stage)}
            />
            {/* Render an arrow after every node except the last */}
            {index < stages.length - 1 && (
              <span className="pipeline-graph-arrow" aria-hidden="true">→</span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
